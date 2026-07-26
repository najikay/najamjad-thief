"""Tests for the orchestrator: turn loop, information discipline, end conditions."""

import pytest

from najamjad_agent.constants import EndReason, Move, Phase, Role
from tests.fakes.orchestration import build_orchestrator


def _turn(step: int = 1, **fields) -> dict:
    """A message shaped as a peer may legitimately send it."""
    return {"step": step, "sender": "thief", "commit": "a" * 64, "hint": "near the river", **fields}


def test_thief_moves_first() -> None:
    thief, _, _ = build_orchestrator(role=Role.THIEF)
    cop, _, _ = build_orchestrator(role=Role.COP)
    assert thief.moves_first
    assert not cop.moves_first


def test_a_turn_sends_the_commitment_and_public_evidence_only() -> None:
    """The core information rule: position and move stay sealed until audit."""
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH])
    orchestrator.take_turn()
    assert orchestrator.fsm.phase is Phase.AWAITING_REVEAL
    assert len(transport.sent) == 1
    message = transport.sent[0]
    assert set(message) >= {"step", "sender", "commit", "hint", "smell_grid"}
    assert "position" not in message
    assert "move" not in message
    assert "payload" not in message
    assert "nonce" not in message


def test_nothing_we_transmit_ever_reveals_our_position() -> None:
    """Regression guard for the leak: scan every byte we would send."""
    orchestrator, transport, _ = build_orchestrator(
        role=Role.COP, moves=[Move.SOUTH, Move.EAST], inbox=[_turn(1), _turn(2)]
    )
    for _ in range(2):
        orchestrator.take_turn()
        orchestrator.receive_turn()
    wire = str(transport.sent)
    assert "position" not in wire
    assert "MOVE:" not in wire
    assert "intent" not in wire


def test_move_updates_position_and_lays_scent() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH])
    orchestrator.take_turn()
    assert orchestrator.state.own_position == (1, 0)
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == 0.9


def test_the_scent_snapshot_we_publish_carries_no_coordinates_of_ours() -> None:
    """Scent is evidence, not a position: it is a map of intensities only."""
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH])
    orchestrator.take_turn()
    grid = transport.sent[0]["smell_grid"]
    assert grid, "we do emit scent"
    assert all(isinstance(key, str) and "," in key for key in grid)


def test_illegal_brain_move_is_replaced_not_transmitted() -> None:
    """A hallucinating strategy must never cost us a technical loss."""
    events: list[dict] = []
    orchestrator, transport, _ = build_orchestrator(
        role=Role.COP, moves=[Move.NORTH], events=events
    )
    orchestrator.take_turn()
    assert orchestrator.state.own_position == (0, 0), "stayed instead of walking off-board"
    assert any(event.get("event") == "move.illegal_rejected" for event in events)
    assert transport.sent[0]["commit"]


def test_cop_barrier_placement_is_declared_publicly():
    """Book rules 15-16: barriers are the one action we must announce."""
    orchestrator, transport, _ = build_orchestrator(
        role=Role.COP, moves=[Move.STAY], barriers=[(0, 1)]
    )
    orchestrator.take_turn()
    assert transport.sent[0]["barrier_placed"] == [0, 1]
    assert orchestrator.state.board.is_blocked((0, 1))
    assert orchestrator.state.barriers_left == 13


def test_thief_never_places_a_barrier() -> None:
    orchestrator, transport, _ = build_orchestrator(
        role=Role.THIEF, moves=[Move.SOUTH], barriers=[(3, 4)]
    )
    orchestrator.take_turn()
    assert "barrier_placed" not in transport.sent[0]


def test_capture_claim_is_only_made_from_our_own_cell() -> None:
    """Book rule 22: a claim about a cell we are not on is not expressible."""
    orchestrator, transport, _ = build_orchestrator(role=Role.COP, moves=[Move.STAY])
    orchestrator.state.opponent_estimate = (5, 5)
    orchestrator.take_turn()
    assert transport.sent[0]["capture_claim"] is False


def test_receive_turn_absorbs_hint_and_scent() -> None:
    message = _turn(smell_grid={"3,3": 0.9})
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[message])
    orchestrator.receive_turn()
    assert orchestrator.state.last_opponent_hint == "near the river"
    assert orchestrator.state.opponent_scent.intensity_at((3, 3)) > 0


def test_our_estimate_of_them_comes_from_belief_not_from_a_message() -> None:
    """No position is transmitted, so belief is the only source."""
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[_turn(smell_grid={"5,5": 0.9})])
    orchestrator.receive_turn()
    assert orchestrator.state.opponent_estimate == orchestrator.state.belief.peak()


def test_declared_opponent_barrier_is_honoured() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, inbox=[_turn(barrier_placed=[3, 4])])
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
        role=Role.COP, moves=[Move.SOUTH], inbox=[_turn()]
    )
    orchestrator.take_turn()
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == 0.9, "no decay mid-turn"
    orchestrator.receive_turn()
    assert orchestrator.state.own_scent.intensity_at((1, 0)) == pytest.approx(0.81)
    assert orchestrator.state.full_turns == 1


def test_the_thief_answers_a_landing_capture_claim_honestly() -> None:
    """Rules 21-22: the claim settles only if the cop is truly on our cell."""
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, position=(3, 3))
    orchestrator._transport.inbox.append(_turn(capture_claim=True, claimed_cell=[3, 3]))

    # The game does not close on receipt: the cop is owed an honest answer and
    # cannot otherwise learn whether its claim landed. The answer rides on our
    # next turn, and the game closes once it has gone out.
    assert orchestrator.receive_turn() is None
    assert orchestrator.state.pending_end is EndReason.CAPTURE

    assert orchestrator.take_turn() is EndReason.CAPTURE
    assert orchestrator.fsm.phase is Phase.GAME_END
    sent = orchestrator._transport.sent[-1]
    assert sent["claim_response"] is True


def test_a_capture_claim_from_elsewhere_does_not_end_the_game() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.THIEF, position=(3, 3))
    orchestrator._transport.inbox.append(_turn(capture_claim=True, claimed_cell=[0, 0]))
    assert orchestrator.receive_turn() is None


def test_barrier_capture_ends_the_game() -> None:
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, moves=[Move.STAY], barriers=[(0, 1)], position=(0, 0)
    )
    orchestrator.state.opponent_estimate = (0, 1)
    assert orchestrator.take_turn() is EndReason.CAPTURE
    assert orchestrator.state.ledger.vault.audit_open, "audit opens on game end"


def test_survival_threshold_ends_the_game() -> None:
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[_turn()])
    orchestrator.state.full_turns = 34

    assert orchestrator.receive_turn() is None
    assert orchestrator.state.pending_end is EndReason.SURVIVAL

    # Declared to the opponent, so both sides close on survival rather than one
    # of them timing out and filing a contradictory result.
    assert orchestrator.take_turn() is EndReason.SURVIVAL
    assert orchestrator._transport.sent[-1]["win_claim"] == "survival"


def test_events_carry_step_correlation() -> None:
    events: list[dict] = []
    orchestrator, _, _ = build_orchestrator(role=Role.COP, moves=[Move.SOUTH], events=events)
    orchestrator.take_turn()
    sent = [event for event in events if event.get("event") == "turn.sent"]
    assert sent and sent[0]["step"] == 1


def test_a_peer_protocol_error_forfeits_cleanly() -> None:
    """Their broken protocol must resolve our game, not crash it."""
    orchestrator, _, _ = build_orchestrator(role=Role.COP, inbox=[_turn(1), _turn(1)])
    orchestrator.receive_turn()
    assert orchestrator.receive_turn() is EndReason.TAMPER_FORFEIT
    assert orchestrator.fsm.phase is Phase.TECHNICAL_LOSS
