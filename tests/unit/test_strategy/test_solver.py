"""Tests for the exact solve — the game-theoretic answer, not a heuristic.

The whole point of computing this rather than tuning toward it is that the
result is checkable against known theory. A 7x7 grid is the Cartesian product
of two paths, and the cop number of a product of two trees is 2 (Maamoun &
Meyniel), so a lone cop must not be able to force a capture from any separated
position. A 1xN path, by contrast, is cop-win from everywhere. If the solver
disagreed with either, it would be the solver that is wrong.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.solver import (
    cop_can_force_capture,
    losing_states,
    safe_landings,
    solve,
)
from tests.fakes.orchestration import build_state


@pytest.fixture()
def board() -> Board:
    return build_state(Role.THIEF).board


def separated(losing) -> set:
    """Cop-win positions where the two are not already on the same cell."""
    return {(cop, thief) for cop, thief in losing if cop != thief}


def test_one_cop_cannot_force_a_capture_on_an_intact_grid(board: Board) -> None:
    """The headline, and it matches the published cop number of 2."""
    assert separated(solve(board)) == set()


def test_the_only_cop_wins_are_positions_already_shared(board: Board) -> None:
    losing = solve(board)

    assert len(losing) == 49
    assert all(cop == thief for cop, thief in losing)


def test_a_corridor_is_cop_win_from_everywhere(board: Board) -> None:
    """The control. A 1xN path IS cop-win, so a solver that says otherwise is broken.

    Built by walling every row but one, which leaves a 7-cell path.
    """
    corridor = board
    for row in range(7):
        if row == 3:
            continue
        for col in range(7):
            corridor = corridor.with_barrier((row, col))

    losing = solve(corridor)

    assert len(separated(losing)) > 0, "a path must be catchable"
    assert cop_can_force_capture(corridor, (3, 0), (3, 6))


def test_a_sealed_pocket_is_cop_win_only_when_it_is_a_tree(board: Board) -> None:
    """Barriers break the theorem — but only the right barriers, and that matters.

    My first version of this test sealed a 2x2 block and asserted the cop wins
    inside it. It does not: a 2x2 block is a 4-cycle, and cycles are the
    textbook example of a graph that is *not* cop-win — the thief simply runs
    round. The solver was right and the test was wrong.

    Which is the whole lesson for the cop's barrier planner: walling cells to
    shrink the thief's room achieves nothing on its own. Only making the
    remaining region **acyclic** does, because every tree is cop-win.
    """
    pocket = board
    for cell in [(1, 0), (1, 1), (1, 2), (0, 3)]:
        pocket = pocket.with_barrier(cell)

    assert cop_can_force_capture(pocket, (0, 2), (0, 0)), "a sealed 1x3 path is cop-win"

    ring = board
    for cell in [(0, 2), (1, 2), (2, 2), (2, 1), (2, 0)]:
        ring = ring.with_barrier(cell)

    assert not cop_can_force_capture(ring, (0, 1), (0, 0)), "a sealed 2x2 ring is not"


def test_an_intact_grid_offers_the_thief_a_safe_move_everywhere(board: Board) -> None:
    """If any separated position had no safe landing, survival would not hold."""
    for cop in board.cells():
        for thief in board.cells():
            if cop == thief:
                continue
            assert safe_landings(board, cop, thief), f"no safe move from {cop} vs {thief}"


def test_a_safe_landing_is_never_the_cop_s_own_cell(board: Board) -> None:
    assert (0, 0) not in safe_landings(board, (0, 0), (0, 1))


def test_the_solve_is_cached_per_barrier_layout(board: Board) -> None:
    """A fresh solve per turn would cost 40 ms; per barrier layout costs nothing."""
    first = losing_states(board)
    second = losing_states(Board(board.params, board.barriers))

    assert first is second


def test_adding_a_barrier_reopens_the_question(board: Board) -> None:
    """The cache must key on the walls, or a barrier would be invisible to it."""
    walled = board.with_barrier((3, 3))

    assert losing_states(walled) is not losing_states(board)
