"""Tests for move application, legality filtering, and diagonal rejection."""

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import IllegalMoveError, apply_move, legal_moves


def _boxed(board: Board) -> Board:
    """A board where (3,3) is enclosed by barriers on all four sides."""
    for cell in [(2, 3), (4, 3), (3, 2), (3, 4)]:
        board = board.with_barrier(cell)
    return board


@pytest.mark.parametrize(
    ("move", "expected"),
    [
        (Move.NORTH, (2, 3)),
        (Move.SOUTH, (4, 3)),
        (Move.EAST, (3, 4)),
        (Move.WEST, (3, 2)),
        (Move.STAY, (3, 3)),
    ],
)
def test_apply_move_walks_one_cell(board: Board, move: Move, expected: tuple) -> None:
    assert apply_move(board, (3, 3), move) == expected


def test_apply_move_accepts_the_wire_string(board: Board) -> None:
    """Opponent payloads arrive as strings; the domain accepts the fixed vocabulary."""
    assert apply_move(board, (3, 3), "N") == (2, 3)


def test_move_off_board_is_illegal(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="off-board"):
        apply_move(board, (0, 0), Move.NORTH)


def test_move_into_barrier_is_illegal(board: Board) -> None:
    with pytest.raises(IllegalMoveError, match="barrier"):
        apply_move(board.with_barrier((2, 3)), (3, 3), Move.NORTH)


def test_stay_is_legal_even_when_surrounded(board: Board) -> None:
    assert apply_move(_boxed(board), (3, 3), Move.STAY) == (3, 3)


def test_diagonal_encodings_are_rejected(board: Board) -> None:
    """Book rules 13-14: no diagonal move exists, whatever the wire encoding."""
    for encoding in ("NE", "SW", "N-E", "diagonal", "NORTHEAST"):
        with pytest.raises(IllegalMoveError, match="unknown move"):
            apply_move(board, (3, 3), encoding)


def test_illegal_move_error_carries_a_typed_reason(board: Board) -> None:
    """The protocol layer needs a machine-readable reason to enforce physics."""
    with pytest.raises(IllegalMoveError) as caught:
        apply_move(board, (0, 0), Move.WEST)
    assert caught.value.reason == "off-board"


def test_legal_moves_at_open_centre_includes_all_five(board: Board) -> None:
    assert set(legal_moves(board, (3, 3))) == set(Move)


def test_legal_moves_at_corner_excludes_off_board(board: Board) -> None:
    assert set(legal_moves(board, (0, 0))) == {Move.SOUTH, Move.EAST, Move.STAY}


def test_legal_moves_excludes_barrier_cells(board: Board) -> None:
    assert set(legal_moves(board.with_barrier((0, 1)), (0, 0))) == {Move.SOUTH, Move.STAY}


def test_legal_moves_always_contains_stay_when_in_bounds(board: Board) -> None:
    """STAY is never blocked, so an agent always has at least one legal action."""
    assert set(legal_moves(_boxed(board), (3, 3))) == {Move.STAY}


def test_mobile_moves_is_empty_when_boxed_in(board: Board) -> None:
    """Immobilisation (book rule 47) looks only at moves that change the cell."""
    assert legal_moves(_boxed(board), (3, 3), mobile_only=True) == ()
    assert legal_moves(board, (3, 3), mobile_only=True) != ()
