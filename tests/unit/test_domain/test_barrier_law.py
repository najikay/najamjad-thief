"""Tests for the Barrier Law and opponent-move (physics) enforcement."""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import (
    BarrierPlacement,
    IllegalMoveError,
    place_barrier,
    validate_opponent_step,
)
from najamjad_agent.domain.params import GameParams


def _rows(rows: tuple[int, ...], width: int) -> set:
    return {(row, col) for row in rows for col in range(width)}


def test_cop_may_place_on_own_or_adjacent_cell(board: Board) -> None:
    for target in [(3, 3), (2, 3), (4, 3), (3, 2), (3, 4)]:
        placement = place_barrier(board, Role.COP, (3, 3), target)
        assert isinstance(placement, BarrierPlacement)
        assert placement.board.is_blocked(target)


def test_cop_may_not_place_two_cells_away(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="out of reach"):
        place_barrier(board, Role.COP, (3, 3), (1, 3))


def test_cop_may_not_place_diagonally(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="out of reach"):
        place_barrier(board, Role.COP, (3, 3), (2, 2))


def test_thief_may_never_place_a_barrier(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="cop"):
        place_barrier(board, Role.THIEF, (3, 3), (3, 4))


def test_placement_off_board_is_rejected(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="off-board"):
        place_barrier(board, Role.COP, (0, 0), (-1, 0))


def test_placement_on_existing_barrier_is_rejected(board: Board) -> None:
    once = place_barrier(board, Role.COP, (3, 3), (3, 4)).board
    with pytest.raises(IllegalMoveError, match="already"):
        place_barrier(once, Role.COP, (3, 3), (3, 4))


def test_budget_is_enforced_from_config(params: GameParams) -> None:
    """Appendix F Table 15: the barrier quota is a hard resource limit."""
    exhausted = Board(params, barriers=_rows((5, 6), 7))
    assert exhausted.barrier_count == params.max_barriers == 14
    with pytest.raises(IllegalMoveError, match="budget"):
        place_barrier(exhausted, Role.COP, (0, 0), (0, 1))


def test_placement_succeeds_while_budget_remains(params: GameParams) -> None:
    nearly = Board(params, barriers=_rows((6,), 7) | _rows((5,), 6))
    assert nearly.barrier_count == 13
    assert place_barrier(nearly, Role.COP, (0, 0), (0, 1)).board.barrier_count == 14


def test_placement_declares_the_exact_cell(board: Board) -> None:
    """Book rules 15-16: every placement yields a truthful public declaration."""
    assert place_barrier(board, Role.COP, (3, 3), (3, 4)).declaration == {"barrier_placed": [3, 4]}


def test_opponent_step_of_one_orthogonal_cell_is_accepted(board: Board) -> None:
    assert validate_opponent_step(board, (3, 3), (3, 4)) is None


def test_opponent_stay_is_accepted(board: Board) -> None:
    assert validate_opponent_step(board, (3, 3), (3, 3)) is None


def test_opponent_teleport_is_rejected(board: Board) -> None:
    assert validate_opponent_step(board, (3, 3), (5, 5)) == "teleport"


def test_opponent_two_cell_straight_dash_is_rejected(board: Board) -> None:
    assert validate_opponent_step(board, (3, 3), (3, 5)) == "teleport"


def test_opponent_diagonal_step_is_rejected(board: Board) -> None:
    assert validate_opponent_step(board, (3, 3), (2, 2)) == "diagonal"


def test_opponent_step_onto_barrier_is_rejected(board: Board) -> None:
    assert validate_opponent_step(board.with_barrier((3, 4)), (3, 3), (3, 4)) == "barrier"


def test_opponent_step_off_board_is_rejected(board: Board) -> None:
    assert validate_opponent_step(board, (0, 0), (-1, 0)) == "off-board"
