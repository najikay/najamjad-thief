"""Barrier economics, barriers as information, and the cop's edge cases.

Fourteen barriers is the whole budget for thirty-five steps, and the sweep says
this is the dial that decides matches: 0.05 captured 4 % of games, 0.40 captured
100 %. The reason is counter-intuitive and worth encoding in tests rather than
prose — **a barrier is impassable for both sides**, so spending one on weak
evidence does not trap the thief, it fences us away from it.

The edge cases below are the ones a real match produces: an exhausted quota, a
belief spread flat across the board, and a thief standing next to us.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.strategy.cop_brain import CopBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The fields a cop brain reads off a turn."""

    def __init__(self, board, position, belief=None, barriers_left=14):
        self.board = board
        self.own_position = position
        self.belief = belief or {}
        self.legal = legal_moves(board, position)
        self.barriers_left = barriers_left
        self.role = "police"


def board_of(*barriers):
    """A fresh board with these cells walled."""
    board = build_state(Role.COP).board
    for cell in barriers:
        board = board.with_barrier(cell)
    return board


# --------------------------------------------------------- economics (T-1417)


def test_a_barrier_is_not_spent_on_weak_evidence():
    """The defect that cost a third of our games for weeks.

    A wall on a guess is not aggression — it is self-harm, because the cell
    becomes impassable to us too.
    """
    board = board_of()
    brain = CopBrain()

    assert brain.pick_barrier(Facts(board, (1, 4), {(3, 4): 0.05})) is None


def test_a_barrier_is_spent_when_the_evidence_is_strong():
    board = board_of()

    assert CopBrain().pick_barrier(Facts(board, (1, 4), {(3, 4): 0.95})) is not None


@pytest.mark.parametrize("threshold,mass,expected", [
    (0.40, 0.95, True), (0.40, 0.20, False), (0.10, 0.20, True),
])
def test_the_threshold_is_what_decides(threshold, mass, expected):
    """Its effect must be visible, or the sweep is measuring nothing."""
    brain = CopBrain(barrier_threshold=threshold)
    placed = brain.pick_barrier(Facts(board_of(), (1, 4), {(3, 4): mass}))

    assert (placed is not None) is expected


def test_an_exhausted_quota_places_nothing():
    """Fourteen is the budget for the whole mini-game (T-1426)."""
    assert CopBrain().pick_barrier(Facts(board_of(), (1, 4), {(3, 4): 0.95}, barriers_left=0)) is None


def test_the_quota_is_respected_rather_than_assumed():
    """A brain that ignored `barriers_left` would place an illegal wall and
    have the orchestrator refuse it — losing the turn instead of moving."""
    brain = CopBrain()
    with_quota = brain.pick_barrier(Facts(board_of(), (1, 4), {(3, 4): 0.95}, barriers_left=1))
    without = brain.pick_barrier(Facts(board_of(), (1, 4), {(3, 4): 0.95}, barriers_left=0))

    assert with_quota is not None and without is None


# ------------------------------------------------- barriers as information


def test_a_placed_barrier_is_never_placed_on_ourselves():
    """Walling our own cell would immobilise the pursuer."""
    board = board_of()
    placed = CopBrain().pick_barrier(Facts(board, (3, 4), {(3, 4): 0.95}))

    assert placed != (3, 4)


def test_a_barrier_is_never_placed_on_an_existing_one():
    """Spending a second wall on the same cell buys nothing and costs quota."""
    board = board_of((3, 4))
    placed = CopBrain().pick_barrier(Facts(board, (1, 4), {(3, 4): 0.95}))

    assert placed != (3, 4)


def test_the_wall_lands_where_the_belief_is():
    """A barrier placed away from the thief tells us nothing and blocks us."""
    placed = CopBrain().pick_barrier(Facts(board_of(), (1, 4), {(3, 4): 0.95}))

    assert placed is not None
    assert abs(placed[0] - 3) + abs(placed[1] - 4) <= 2


# ------------------------------------------------------- edge cases (T-1426)


def test_no_belief_at_all_places_no_barrier():
    """Nothing to wall against; spending here is pure loss."""
    assert CopBrain().pick_barrier(Facts(board_of(), (3, 3), {})) is None


def test_a_uniform_belief_places_no_barrier():
    """Belief spread flat over the board is the same as knowing nothing, and
    the threshold is what expresses that."""
    board = board_of()
    flat = dict.fromkeys(board.cells(), 1.0 / len(list(board.cells())))

    assert CopBrain().pick_barrier(Facts(board, (3, 3), flat)) is None


def test_an_empty_legal_set_yields_stay_rather_than_raising():
    """The orchestrator filters legality; a bug here must be a weak move."""
    facts = Facts(board_of(), (0, 0))
    facts.legal = ()

    assert CopBrain().pick_move(facts) is Move.STAY


def test_no_belief_still_yields_a_legal_move():
    """Before the first scent arrives there is nothing to chase."""
    facts = Facts(board_of(), (3, 3))

    assert CopBrain().pick_move(facts) in facts.legal


def test_a_thief_believed_adjacent_is_stepped_on_not_walled():
    """A capture the opponent confirms beats enclosure it may not honour."""
    board = board_of()
    facts = Facts(board, (3, 3), {(3, 4): 0.95})
    brain = CopBrain()

    assert brain.pick_barrier(facts) is None
    assert brain.pick_move(facts) is Move.EAST


def test_the_policy_is_deterministic_under_identical_facts():
    """Replay is a graded deliverable."""
    brain = CopBrain()
    facts = Facts(board_of(), (0, 0), {(4, 4): 0.6})

    assert brain.pick_move(facts) is brain.pick_move(facts)
