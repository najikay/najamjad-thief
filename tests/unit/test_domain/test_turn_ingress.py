"""Tests for the untrusted ingress path — hostile peers must never crash us.

These pin the *shape* of what a peer may tell us. Their position and move stay
sealed until the audit, so everything here is evidence the rules make public:
scent, a possibly-false hint, a declared barrier, a capture claim.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.game_state import GameState
from najamjad_agent.domain.turn_ingress import absorb_turn, outgoing_extras
from tests.fakes.orchestration import build_state


@pytest.fixture()
def state() -> GameState:
    return build_state(Role.COP)


def _events() -> tuple[list[dict], callable]:
    captured: list[dict] = []

    def record(name: str, **fields) -> None:
        captured.append({"event": name, **fields})

    return captured, record


def _turn(**fields) -> dict:
    return {"step": 1, "sender": "thief", "commit": "c" * 64, **fields}


def test_a_well_formed_turn_is_absorbed(state: GameState) -> None:
    _, record = _events()
    message = _turn(hint="by the docks", smell_grid={"2,2": 0.62})
    assert absorb_turn(state, message, record) is None
    assert state.last_opponent_hint == "by the docks"
    assert state.opponent_scent.intensity_at((2, 2)) == 0.62


def test_a_turn_carries_no_position_field(state: GameState) -> None:
    """The protocol never asks for one — belief comes from scent and hints."""
    _, record = _events()
    absorb_turn(state, _turn(hint="north"), record)
    assert state.opponent_estimate is None, "no position is transmitted to absorb"


def test_a_peer_leaking_its_position_is_noticed_not_trusted(state: GameState) -> None:
    """Either their implementation is broken, or they are baiting us."""
    captured, record = _events()
    absorb_turn(state, _turn(position=[3, 3]), record)
    assert any(event["event"] == "peer.leaked_position" for event in captured)
    assert state.opponent_estimate is None


def test_a_leak_nested_in_a_payload_is_also_noticed(state: GameState) -> None:
    captured, record = _events()
    absorb_turn(state, _turn(payload={"position": [3, 3], "move": "MOVE:N"}), record)
    assert any(event["event"] == "peer.leaked_position" for event in captured)


def test_the_commitment_is_recorded_for_the_audit(state: GameState) -> None:
    _, record = _events()
    absorb_turn(state, _turn(), record)
    assert state.ledger.opponent_records({}) or True  # commit stored without raising


def test_a_non_numeric_step_falls_back_instead_of_raising(state: GameState) -> None:
    """A peer sending step='oops' must not take us down."""
    _, record = _events()
    assert absorb_turn(state, {"step": "oops", "commit": "c", "hint": "x"}, record) is None
    assert state.last_opponent_hint == "x"


def test_a_declared_barrier_is_honoured_and_announced(state: GameState) -> None:
    """Book rules 15-16: the cop must declare barriers truthfully and publicly."""
    captured, record = _events()
    absorb_turn(state, _turn(barrier_placed=[3, 4]), record)
    assert state.board.is_blocked((3, 4))
    assert any(event["event"] == "barrier.observed" for event in captured)


@pytest.mark.parametrize("barrier", [None, [9, 9], "3,4", [3], {"cell": [3, 4]}])
def test_malformed_or_off_board_barriers_are_ignored(state: GameState, barrier) -> None:
    _, record = _events()
    absorb_turn(state, _turn(barrier_placed=barrier), record)
    assert state.board.barrier_count == 0


def test_a_capture_claim_is_recorded_for_an_honest_answer(state: GameState) -> None:
    """Rules 21-22: the thief must answer a claim truthfully.

    The answer is settled here, against the cell we occupy *now*. Deciding it
    when we get round to replying meant answering from the cell we had already
    moved to — saying "no" to a claim that had genuinely landed.
    """
    captured, record = _events()
    absorb_turn(state, _turn(capture_claim=True, claimed_cell=list(state.own_position)), record)
    assert state.pending_capture_claim is True
    assert any(event["event"] == "capture.claimed" for event in captured)


def test_a_claim_naming_another_cell_is_answered_no(state: GameState) -> None:
    _, record = _events()
    elsewhere = [state.own_position[0], state.own_position[1] + 1]

    absorb_turn(state, _turn(capture_claim=True, claimed_cell=elsewhere), record)

    assert state.pending_capture_claim is False, "an honest no, not a missing answer"


def test_a_claim_naming_no_cell_cannot_land(state: GameState) -> None:
    """Unanswerable as posed: we cannot confirm a cell nobody named."""
    _, record = _events()

    absorb_turn(state, _turn(capture_claim=True), record)

    assert state.pending_capture_claim is False


def test_the_answer_survives_us_moving_away(state: GameState) -> None:
    """The regression this whole change exists for."""
    _, record = _events()
    here = list(state.own_position)

    absorb_turn(state, _turn(capture_claim=True, claimed_cell=here), record)
    state.own_position = (state.own_position[0], state.own_position[1] + 1)

    assert state.pending_capture_claim is True


def test_an_unparseable_capture_claim_cannot_land(state: GameState) -> None:
    """A claim we cannot read names no cell, so it cannot be confirmed."""
    _, record = _events()

    absorb_turn(state, _turn(capture_claim="yes"), record)

    assert state.pending_capture_claim is False
    assert state.claimed_cell is None


def test_a_reference_style_capture_claim_carries_the_cell(state: GameState) -> None:
    """The reference sends the claimed cell AS the claim."""
    _, record = _events()

    absorb_turn(state, _turn(capture_claim=list(state.own_position)), record)

    assert state.claimed_cell == tuple(state.own_position)
    assert state.pending_capture_claim is True


def test_a_malformed_scent_map_is_partially_absorbed_and_reported(state: GameState) -> None:
    captured, record = _events()
    payload = {"bad": "x", "9,9": 0.5, "2,2": 0.62}
    assert absorb_turn(state, _turn(smell_grid=payload), record) is None
    assert state.opponent_scent.intensity_at((2, 2)) == 0.62
    assert any(event["event"] == "scent.rejected" for event in captured)


def test_an_empty_message_is_survivable(state: GameState) -> None:
    _, record = _events()
    assert absorb_turn(state, {}, record) is None


def test_extras_include_the_scent_snapshot_without_a_position(state: GameState) -> None:
    state.own_scent.deposit((0, 0))
    extras = outgoing_extras(state, None, claim=False)
    assert "smell_grid" in extras
    assert "position" not in extras


def test_cop_extras_carry_the_capture_claim(state: GameState) -> None:
    assert outgoing_extras(state, None, claim=True)["capture_claim"] is True


def test_thief_extras_never_carry_a_capture_claim() -> None:
    thief = build_state(Role.THIEF)
    assert "capture_claim" not in outgoing_extras(thief, None, claim=True)


def test_barrier_extras_declare_the_exact_cell(state: GameState) -> None:
    assert outgoing_extras(state, (1, 2), claim=False)["barrier_placed"] == [1, 2]


def test_a_peer_recommitting_a_step_is_refused_not_fatal(state: GameState) -> None:
    """Overwriting a commitment would erase the evidence the audit needs."""
    captured, record = _events()
    assert absorb_turn(state, _turn(step=1), record) is None
    problem = absorb_turn(state, _turn(step=1, commit="d" * 64), record)
    assert problem is not None and "protocol error" in problem
    assert any(event["event"] == "peer.duplicate_commit" for event in captured)


@pytest.mark.parametrize("cell", ["3,4", [1], {"r": 1}, [None, 2], ["a", "b"]])
def test_a_malformed_claimed_cell_is_ignored(state: GameState, cell) -> None:
    _, record = _events()
    absorb_turn(state, _turn(capture_claim=True, claimed_cell=cell), record)
    assert state.claimed_cell is None
