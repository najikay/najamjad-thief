"""Tests for the orchestrator: turn loop, physics policing, end conditions."""

import pytest

from najamjad_agent.constants import EndReason, Move, Phase, Role
from najamjad_agent.domain.crypto import commit_of
from tests.fakes.orchestration import build_orchestrator


def _turn(step: int, position: list[int], **extra) -> dict:
    payload = {
        "step": step,
        "role": "thief",
        "position": position,
        "move": "MOVE:S",
        "intent": "truth",
        "hint": "near the river",
        "state": "s",
        **extra,
    }
    return {"step": step, "payload": payload, "commit": commit_of(payload, "n" * 32)}


def test_thief_moves_first() -> None:
    thief, _, _ = build_orchestrator(role=Role.THIEF)
    cop, _, _ = build_orchestrator(role=Role.COP)
    assert thief.moves_first
    assert not cop.moves_first


def test_take_turn_walks_the_fsm_and_sends_commit_then_reveal() -> None:
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH])
    orchestrator.take_turn()
    assert orchestrator.fsm.phase is Phase.AWAITING_REVEAL
    assert len(transport.sent) == 2
    assert set(transport.sent[0]) == {"step", "commit"}
    assert "payload" in transport.sent[1]
    assert "nonce" not in transport.sent[1], "nonce must not reach the wire pre-audit"


def test_move_updates_position_and_lays_scent() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH])
    orchestrator.take_turn()
    assert orchestrator.state.own_position == (1, 0)
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == 0.9


def test_illegal_brain_move_is_replaced_not_transmitted() -> None:
    """A hallucinating strategy must never cost us a technical loss."""
    events: list[dict] = []
    orchestrator, transport, _ = build_orchestrator(
        role=Role.COP, moves=[Move.NORTH], events=events
    )
    orchestrator.take_turn()
    assert orchestrator.state.own_position == (0, 0), "stayed instead of walking off-board"
    assert any(event.get("event") == "move.illegal_rejected" for event in events)
    assert transport.sent[1]["payload"]["move"] == "MOVE:STAY"


def test_cop_barrier_placement_is_declared_and_budgeted() -> None:
    orchestrator, transport, _ = build_orchestrator(
        role=Role.COP, moves=[Move.STAY], barriers=[(0, 1)]
    )
    orchestrator.take_turn()
    payload = transport.sent[1]["payload"]
    assert payload["barrier_placed"] == [0, 1]
    assert orchestrator.state.board.is_blocked((0, 1))
    assert orchestrator.state.barriers_left == 13


def test_thief_never_places_a_barrier() -> None:
    orchestrator, transport, _ = build_orchestrator(
        role=Role.THIEF, moves=[Move.SOUTH], barriers=[(3, 4)]
    )
    orchestrator.take_turn()
    assert "barrier_placed" not in transport.sent[1]["payload"]


def test_capture_claim_is_only_made_from_our_own_cell() -> None:
    """Book rule 22: a claim about a cell we are not on is not expressible."""
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, moves=[Move.STAY])
    orchestrator.state.opponent_estimate = (5, 5)
    orchestrator.take_turn()
    assert transport.sent[1]["payload"]["capture_claim"] is False


def test_receive_turn_absorbs_hint_scent_and_position() -> None:
    message = _turn(1, [3, 3], smell_grid={"3,3": 0.9})
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[message])
    orchestrator.state.ledger.record_opponent_commit(0, "seed")
    orchestrator.receive_turn()
    assert orchestrator.state.opponent_estimate == (3, 3)
    assert orchestrator.state.last_opponent_hint == "near the river"
    assert orchestrator.state.opponent_scent.intensity_at((3, 3)) > 0


def test_opponent_teleport_is_caught_and_forfeits() -> None:
    """No referee: we police their physics ourselves (book rules 13-14)."""
    events: list[dict] = []
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, inbox=[_turn(1, [3, 3]), _turn(2, [6, 6])], events=events
    )
    orchestrator.receive_turn()
    assert orchestrator.receive_turn() is EndReason.TAMPER_FORFEIT
    assert orchestrator.fsm.phase is Phase.TECHNICAL_LOSS
    assert any(event.get("event") == "physics.violation" for event in events)


def test_opponent_diagonal_step_is_caught() -> None:
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, inbox=[_turn(1, [3, 3]), _turn(2, [4, 4])]
    )
    orchestrator.receive_turn()
    assert orchestrator.receive_turn() is EndReason.TAMPER_FORFEIT


def test_declared_opponent_barrier_is_honoured() -> None:
    message = _turn(1, [3, 3], barrier_placed=[3, 4])
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, inbox=[message])
    orchestrator.receive_turn()
    assert orchestrator.state.board.is_blocked((3, 4))


def test_timeout_resolves_to_a_clean_technical_loss() -> None:
    """A missed deadline is a failure, never an indefinite wait (book rule 6)."""
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, inbox=[])
    assert orchestrator.receive_turn() is EndReason.TIMEOUT
    assert orchestrator.fsm.phase is Phase.TECHNICAL_LOSS
    assert transport.timeouts == 3, "retried up to the configured budget first"


def test_scent_decays_once_per_full_turn_only() -> None:
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, moves=[Move.SOUTH], inbox=[_turn(1, [3, 3])]
    )
    orchestrator.take_turn()
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == 0.9, "no decay mid-turn"
    orchestrator.receive_turn()
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == pytest.approx(0.81)
    assert orchestrator.state.full_turns == 1


def test_thief_accepts_a_true_capture_claim() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, position=(3, 3))
    orchestrator.state.opponent_estimate = (3, 3)
    message = _turn(1, [3, 3], capture_claim=True)
    orchestrator._transport.inbox.append(message)
    assert orchestrator.receive_turn() is EndReason.CAPTURE
    assert orchestrator.fsm.phase is Phase.GAME_END


def test_thief_ignores_a_capture_claim_on_the_wrong_cell() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, position=(3, 3))
    orchestrator.state.opponent_estimate = (0, 0)
    orchestrator._transport.inbox.append(_turn(1, [0, 0], capture_claim=True))
    assert orchestrator.receive_turn() is None


def test_barrier_capture_ends_the_game() -> None:
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, moves=[Move.STAY], barriers=[(0, 1)], position=(0, 0)
    )
    orchestrator.state.opponent_estimate = (0, 1)
    assert orchestrator.take_turn() is EndReason.CAPTURE
    assert orchestrator.state.ledger.vault.audit_open, "audit opens on game end"


def test_cop_wins_when_the_thief_walls_itself_in() -> None:
    """Book rule 47: a thief with no move that changes its cell is captured."""
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[_turn(1, [0, 0])])
    orchestrator.state.board = (
        orchestrator.state.board.with_barrier((1, 0)).with_barrier((0, 1))
    )
    orchestrator.state.own_position = (6, 6)
    assert orchestrator.receive_turn() is EndReason.CAPTURE
    assert orchestrator.fsm.phase is Phase.GAME_END


def test_survival_threshold_ends_the_game() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[_turn(1, [3, 3])])
    orchestrator.state.full_turns = 34
    assert orchestrator.receive_turn() is EndReason.SURVIVAL


def test_events_carry_step_correlation() -> None:
    events: list[dict] = []
    orchestrator, _, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH], events=events)
    orchestrator.take_turn()
    sent = [event for event in events if event.get("event") == "turn.sent"]
    assert sent and sent[0]["step"] == 1
