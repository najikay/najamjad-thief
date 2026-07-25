"""Tests for the untrusted ingress path — hostile peers must never crash us."""

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


def _message(payload: dict, step: object = 1) -> dict:
    return {"step": step, "payload": payload, "commit": "c" * 64}


def test_absorb_accepts_a_well_formed_turn(state: GameState) -> None:
    _, record = _events()
    assert absorb_turn(state, _message({"position": [3, 3], "hint": "by the docks"}), record) is None
    assert state.opponent_estimate == (3, 3)
    assert state.last_opponent_hint == "by the docks"


def test_message_without_payload_is_ignored_safely(state: GameState) -> None:
    _, record = _events()
    assert absorb_turn(state, {"step": 1, "commit": "c" * 64}, record) is None
    assert state.opponent_estimate is None


def test_non_numeric_step_falls_back_instead_of_raising(state: GameState) -> None:
    """A peer sending step='oops' must not take us down."""
    _, record = _events()
    assert absorb_turn(state, _message({"position": [2, 2]}, step="oops"), record) is None
    assert state.opponent_estimate == (2, 2)


@pytest.mark.parametrize(
    "position",
    [None, "3,3", [3], [1, 2, 3], {"row": 1}, ["a", "b"], [None, None]],
)
def test_malformed_positions_are_ignored_not_fatal(state: GameState, position) -> None:
    _, record = _events()
    assert absorb_turn(state, _message({"position": position}), record) is None
    assert state.opponent_estimate is None


def test_teleport_is_reported_as_a_violation(state: GameState) -> None:
    captured, record = _events()
    absorb_turn(state, _message({"position": [3, 3]}), record)
    problem = absorb_turn(state, _message({"position": [6, 6]}, step=2), record)
    assert problem is not None and "teleport" in problem
    assert captured[-1]["event"] == "physics.violation"


def test_violation_stops_before_absorbing_their_hint(state: GameState) -> None:
    """A cheating peer's other claims must not enter our knowledge either."""
    _, record = _events()
    absorb_turn(state, _message({"position": [3, 3], "hint": "honest"}), record)
    absorb_turn(state, _message({"position": [0, 6], "hint": "poison"}, step=2), record)
    assert state.last_opponent_hint == "honest"


@pytest.mark.parametrize("barrier", [None, [9, 9], "3,4", [3], {"cell": [3, 4]}])
def test_malformed_or_off_board_barriers_are_ignored(state: GameState, barrier) -> None:
    _, record = _events()
    absorb_turn(state, _message({"position": [3, 3], "barrier_placed": barrier}), record)
    assert state.board.barrier_count == 0


def test_declared_barrier_is_recorded_and_announced(state: GameState) -> None:
    captured, record = _events()
    absorb_turn(state, _message({"position": [3, 3], "barrier_placed": [3, 4]}), record)
    assert state.board.is_blocked((3, 4))
    assert captured[-1] == {"event": "barrier.observed", "cell": [3, 4]}


def test_malformed_scent_map_does_not_crash(state: GameState) -> None:
    _, record = _events()
    payload = {"position": [3, 3], "smell_grid": {"bad": "x", "9,9": 0.5, "2,2": 0.62}}
    assert absorb_turn(state, _message(payload), record) is None
    assert state.opponent_scent.intensity_at((2, 2)) == 0.62


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
