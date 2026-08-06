"""Tests for the fair-play monitor — what commit-reveal cannot catch.

Commit-reveal stops an opponent rewriting history. It says nothing about an
opponent who reports truthfully and plays something the rules do not allow, and
that gap turned up in a real series: a peer's cop moved to a new cell *and*
declared a barrier on the same turn, fourteen times, against a Barrier Law that
is explicitly in lieu of moving.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.fair_play import FairPlayMonitor
from tests.fakes.orchestration import build_state


@pytest.fixture()
def board() -> Board:
    return build_state(Role.THIEF).board


@pytest.fixture()
def monitor() -> FairPlayMonitor:
    return FairPlayMonitor(max_barriers=14, hint_max_words=15)


def turn(step, cell=None, barrier=None, hint="heading north past the bridge"):
    message = {"step": step, "hint": hint}
    if cell is not None:
        message["position"] = list(cell)
    if barrier is not None:
        message["barrier_placed"] = list(barrier)
    return message


def test_an_honest_series_is_recorded_as_clean(board, monitor) -> None:
    """"We checked and found nothing" is what makes the report credible."""
    for step, cell in enumerate([(0, 0), (1, 0), (2, 0), (3, 0)], start=1):
        monitor.observe(board, step, turn(step, cell))

    assert monitor.clean
    assert monitor.summary() == {"clean": True, "violations": [], "rules_broken": []}


def test_moving_and_walling_on_one_turn_is_caught(board, monitor) -> None:
    """The real one. Fourteen of these is fourteen free actions."""
    monitor.observe(board, 1, turn(1, (0, 0)))
    found = monitor.observe(board, 2, turn(2, (1, 0), barrier=(0, 0)))

    assert [finding.rule for finding in found] == ["barrier-and-move"]
    assert "in lieu of moving" in found[0].detail


def test_walling_without_moving_is_allowed(board, monitor) -> None:
    """The lawful use of the same power must not be flagged."""
    monitor.observe(board, 1, turn(1, (2, 2)))
    found = monitor.observe(board, 2, turn(2, (2, 2), barrier=(2, 3)))

    assert found == []


def test_a_barrier_out_of_arm_s_reach_is_caught(board, monitor) -> None:
    """`place_barrier` allows own cell or one orthogonal step, nothing further."""
    monitor.observe(board, 1, turn(1, (3, 3)))
    found = monitor.observe(board, 2, turn(2, (3, 3), barrier=(3, 6)))

    assert [finding.rule for finding in found] == ["barrier-out-of-reach"]


def test_spending_more_barriers_than_agreed_is_caught(board, monitor) -> None:
    small = FairPlayMonitor(max_barriers=2, hint_max_words=15)
    for step in range(1, 5):
        small.observe(board, step, turn(step, (3, 3), barrier=(3, 4)))

    assert "barrier-budget" in small.summary()["rules_broken"]


def test_a_two_cell_hop_is_caught(board, monitor) -> None:
    """One move is one step; two is a turn nobody got to answer."""
    monitor.observe(board, 1, turn(1, (0, 0)))
    found = monitor.observe(board, 2, turn(2, (2, 0)))

    assert [finding.rule for finding in found] == ["teleport"]


def test_walking_through_a_barrier_is_caught(board, monitor) -> None:
    walled = board.with_barrier((1, 0))
    monitor.observe(walled, 1, turn(1, (0, 0)))
    found = monitor.observe(walled, 2, turn(2, (1, 0)))

    assert "through-barrier" in [finding.rule for finding in found]


def test_an_off_board_cell_is_caught(board, monitor) -> None:
    found = monitor.observe(board, 1, turn(1, (9, 9)))

    assert [finding.rule for finding in found] == ["off-board"]


def test_a_skipped_step_is_caught(board, monitor) -> None:
    """A jump hides a turn that no audit can reconstruct."""
    monitor.observe(board, 1, turn(1, (0, 0)))
    found = monitor.observe(board, 3, turn(3, (1, 0)))

    assert "step-order" in [finding.rule for finding in found]


def test_an_over_long_hint_is_caught(board, monitor) -> None:
    """The word cap is a negotiated term, so exceeding it is a breach."""
    found = monitor.observe(board, 1, turn(1, (0, 0), hint=" ".join(["word"] * 40)))

    assert [finding.rule for finding in found] == ["hint-length"]


def test_a_malformed_coordinate_is_ignored_rather_than_crashing(board, monitor) -> None:
    """Peers send what they like; the monitor must never be the thing that dies."""
    monitor.observe(board, 1, {"step": 1, "position": "somewhere", "hint": "ok"})
    monitor.observe(board, 2, {"step": 2, "position": [1, "x"], "hint": "ok"})

    assert monitor.clean


def test_findings_carry_the_step_they_happened_on(board, monitor) -> None:
    """Evidence, not a verdict — a human settles this with one message."""
    monitor.observe(board, 4, turn(4, (0, 0)))
    monitor.observe(board, 5, turn(5, (3, 3)))

    assert monitor.findings[0].step == 5
    assert monitor.summary()["clean"] is False


def test_the_monitor_is_actually_wired_into_a_live_state() -> None:
    """The commonest defect in this repo is a class with no production caller.

    `attach_game`, `reconcile` and `record_message` each shipped complete and
    unreferenced. A watchdog nobody calls watches nothing, so this asserts the
    wiring rather than the class.
    """
    from najamjad_agent.domain.params import GameParams
    from najamjad_agent.sdk.state_setup import build_state

    params = GameParams.from_config(
        {
            "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
            "movement_and_barriers": {
                "move_set": ["N", "S", "E", "W", "STAY"],
                "max_barriers": 14,
                "max_moves": 35,
                "survival_threshold": 35,
            },
        }
    )
    state = build_state(params, Role.THIEF, sub_game=1)

    assert state.fair_play is not None
    assert state.fair_play.max_barriers == 14


def test_a_violation_reaches_the_event_log_through_ingress() -> None:
    """End to end: a real breach in a real message must surface as an event."""
    from najamjad_agent.domain.params import GameParams
    from najamjad_agent.domain.turn_ingress import absorb_turn
    from najamjad_agent.sdk.state_setup import build_state

    params = GameParams.from_config(
        {
            "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
            "movement_and_barriers": {
                "move_set": ["N", "S", "E", "W", "STAY"],
                "max_barriers": 14,
                "max_moves": 35,
                "survival_threshold": 35,
            },
        }
    )
    state = build_state(params, Role.THIEF, sub_game=1)
    seen: list[tuple] = []

    absorb_turn(state, {"step": 1, "position": [0, 0], "hint": "north"},
                lambda name, **fields: seen.append((name, fields)))
    absorb_turn(state, {"step": 2, "position": [1, 0], "barrier_placed": [0, 0], "hint": "north"},
                lambda name, **fields: seen.append((name, fields)))

    violations = [fields for name, fields in seen if name == "opponent.violation"]
    assert violations and violations[0]["rule"] == "barrier-and-move"
