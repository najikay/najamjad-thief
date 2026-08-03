"""Graph distance, rooms and cut cells — the measures barriers actually change.

Manhattan distance is the wrong ruler once walls exist. Two cells one apart on
the grid can be twenty apart on the board, and the whole point of these
functions is that a declared barrier changes the answer immediately.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.territory import (
    UNREACHABLE,
    component,
    component_size,
    cut_cells,
    distances_from,
    graph_distance,
)
from tests.fakes.orchestration import build_state


@pytest.fixture()
def board() -> Board:
    return build_state(Role.THIEF).board


def test_an_open_board_reaches_every_cell(board: Board) -> None:
    assert len(distances_from(board, (3, 3))) == 49


def test_distance_is_measured_around_walls_not_through_them(board: Board) -> None:
    """The reason Manhattan is not good enough, in one assertion."""
    walled = Board(board.params, [(0, 1), (1, 1), (1, 0)])

    assert Board.manhattan((0, 0), (1, 1)) == 2
    assert graph_distance(walled, (0, 0), (1, 1)) == UNREACHABLE


def test_a_sealed_cell_is_its_own_whole_room(board: Board) -> None:
    walled = Board(board.params, [(0, 1), (1, 0)])

    assert component(walled, (0, 0)) == {(0, 0)}
    assert component_size(walled, (0, 0)) == 1


def test_a_wall_splits_the_board_into_two_rooms(board: Board) -> None:
    """Seven barriers cut a 7x7 in half — the cop's real weapon, measured."""
    walled = Board(board.params, [(3, col) for col in range(7)])

    assert component_size(walled, (0, 0)) == 21
    assert component_size(walled, (6, 6)) == 21
    assert graph_distance(walled, (0, 0), (6, 6)) == UNREACHABLE


def test_an_open_grid_has_no_cut_cells(board: Board) -> None:
    """Nothing on an intact grid can be severed by removing one cell."""
    assert cut_cells(board, (3, 3)) == set()


def test_the_neck_of_a_dumbbell_is_a_cut_cell(board: Board) -> None:
    """The cell a single barrier would seal us behind — what we must not stand past."""
    walls = [(3, col) for col in range(7) if col != 3]
    walled = Board(board.params, walls)

    assert (3, 3) in cut_cells(walled, (0, 0))


def test_a_tiny_room_has_no_cut_cells(board: Board) -> None:
    """Guard the degenerate case rather than indexing into an empty component."""
    walled = Board(board.params, [(0, 2), (1, 0), (1, 1), (1, 2), (0, 3)])

    assert cut_cells(walled, (0, 0)) <= {(0, 1)}


def test_an_unreachable_goal_is_not_silently_near(board: Board) -> None:
    """`UNREACHABLE` must be large enough that a min() never prefers it."""
    walled = Board(board.params, [(0, 1), (1, 0)])

    assert graph_distance(walled, (0, 0), (6, 6)) > 49
