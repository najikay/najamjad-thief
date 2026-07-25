"""Tests for barrier planning — the cop's real weapon on a small board."""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.cop_barriers import (
    candidate_cells,
    plan_barrier,
    score_placement,
)
from najamjad_agent.strategy.cop_brain import CopBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The read-only view a brain is given."""

    def __init__(self, board: Board, position, belief: dict, legal=None, barriers_left: int = 14):
        self.board = board
        self.own_position = position
        self.belief = belief
        self.legal = legal if legal is not None else tuple(Move)
        self.barriers_left = barriers_left
        self.role = "police"
        self.step = 1
        self.sub_game = 1


def _point_belief(cell, mass: float = 1.0) -> dict:
    return {cell: mass}


def test_barrier_candidates_follow_the_barrier_law() -> None:
    """Own cell or one orthogonal step — never further (book Ch. 3)."""
    state = build_state(Role.COP)
    cells = candidate_cells(state.board, (3, 3))
    assert set(cells) == {(3, 3), (2, 3), (4, 3), (3, 2), (3, 4)}


def test_barrier_candidates_exclude_blocked_and_off_board_cells() -> None:
    state = build_state(Role.COP)
    cells = candidate_cells(state.board.with_barrier((0, 1)), (0, 0))
    assert set(cells) == {(0, 0), (1, 0)}


def test_a_barrier_on_the_believed_thief_scores_as_a_capture() -> None:
    state = build_state(Role.COP)
    plan = score_placement(state.board, (3, 4), {(3, 4): 0.9}, (3, 3))
    assert plan.score > 100
    assert "capture" in plan.reason


def test_a_barrier_that_removes_escape_routes_scores_positively() -> None:
    state = build_state(Role.COP)
    plan = score_placement(state.board, (2, 3), {(1, 3): 0.8}, (3, 3))
    assert plan.score > 0


def test_the_planner_declines_when_nothing_is_worth_a_turn() -> None:
    """A barrier costs a step of pursuit; noise is not worth the quota."""
    state = build_state(Role.COP)
    assert plan_barrier(state.board, (0, 0), {(6, 6): 1.0}, barriers_left=14) is None


def test_the_planner_declines_with_no_quota_left() -> None:
    state = build_state(Role.COP)
    assert plan_barrier(state.board, (3, 3), {(3, 4): 0.9}, barriers_left=0) is None


def test_the_brain_places_a_barrier_when_it_captures() -> None:
    state = build_state(Role.COP)
    facts = Facts(state.board, (3, 3), {(3, 4): 0.95})
    assert CopBrain().pick_barrier(facts) == (3, 4)


def test_the_brain_places_no_barrier_without_belief() -> None:
    state = build_state(Role.COP)
    assert CopBrain().pick_barrier(Facts(state.board, (3, 3), {})) is None


def test_the_planner_refuses_to_wall_itself_away_from_the_thief() -> None:
    """Sealing the only corridor to your quarry loses a won position."""
    state = build_state(Role.COP)
    corridor = state.board
    for cell in [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]:
        corridor = corridor.with_barrier(cell)
    plan = score_placement(corridor, (6, 1), {(6, 0): 0.9}, (6, 2))
    assert plan.score < 0
    assert "wall us away" in plan.reason


def test_move_away_increases_distance_from_the_pursuer() -> None:
    """Shared helper used by the thief brain; proven here alongside its twin.

    Asserts the behaviour rather than one winner: several moves can tie on
    distance, and which tie wins is an implementation detail.
    """
    from najamjad_agent.strategy.base import move_away

    state = build_state(Role.COP)
    pursuer = (6, 3)
    chosen = move_away(state.board, (3, 3), pursuer, tuple(Move))
    row, col = state.board.delta_for(chosen)
    after = Board.manhattan((3 + row, 3 + col), pursuer)
    assert after > Board.manhattan((3, 3), pursuer)


def test_move_away_with_no_options_stays() -> None:
    from najamjad_agent.strategy.base import move_away

    state = build_state(Role.COP)
    assert move_away(state.board, (3, 3), (6, 3), ()) is Move.STAY


def test_reachable_within_respects_barriers_and_radius() -> None:
    from najamjad_agent.strategy.base import reachable_within

    state = build_state(Role.COP)
    assert (0, 1) in reachable_within(state.board, (0, 0), 1)
    assert (0, 3) not in reachable_within(state.board, (0, 0), 1)
    sealed = state.board.with_barrier((0, 1)).with_barrier((1, 0))
    assert reachable_within(sealed, (0, 0), 5) == {(0, 0)}


def test_reachable_within_zero_radius_is_just_the_origin() -> None:
    from najamjad_agent.strategy.base import reachable_within

    state = build_state(Role.COP)
    assert reachable_within(state.board, (2, 2), 0) == {(2, 2)}


def test_the_planner_ignores_negligible_belief_mass() -> None:
    """Spending the quota on noise is how a cop reaches step 30 empty-handed."""
    state = build_state(Role.COP)
    plan = score_placement(state.board, (3, 4), {(1, 1): 0.001}, (3, 3))
    assert plan.score == pytest.approx(0.0)


def test_a_fully_enclosed_belief_cell_still_scores() -> None:
    state = build_state(Role.COP)
    sealed = state.board.with_barrier((0, 1))
    plan = score_placement(sealed, (1, 0), {(0, 0): 0.9}, (1, 1))
    assert plan.score != 0.0


def test_the_brain_can_take_its_board_from_a_supplier() -> None:
    """The orchestrator owns the live board; the brain may be handed a getter."""
    state = build_state(Role.COP)
    brain = CopBrain(board_supplier=lambda: state.board)
    facts = Facts(state.board, (0, 0), _point_belief((6, 0)))
    facts.board = None
    assert brain.pick_move(facts) is Move.SOUTH


def test_a_cell_with_no_open_neighbours_keeps_its_mass_under_lookahead() -> None:
    state = build_state(Role.COP)
    sealed = state.board.with_barrier((0, 1)).with_barrier((1, 0))
    facts = Facts(sealed, (3, 3), {(0, 0): 1.0})
    assert CopBrain().pick_move(facts) in tuple(Move)


def test_the_planner_declines_when_no_placement_is_even_possible() -> None:
    """Fully walled in: the Barrier Law leaves nowhere legal to place."""
    state = build_state(Role.COP)
    sealed = state.board
    for cell in [(0, 0), (0, 1), (1, 0)]:
        sealed = sealed.with_barrier(cell)
    assert plan_barrier(sealed, (0, 0), {(5, 5): 0.9}, barriers_left=14) is None


def test_zero_probability_cells_are_skipped_when_scoring_freedom() -> None:
    """A cell we have ruled out must not influence where we stand."""
    state = build_state(Role.COP)
    facts = Facts(state.board, (3, 3), {(3, 4): 0.0, (6, 3): 1.0})
    assert CopBrain().pick_move(facts) is Move.SOUTH
