"""Tests for the board: bounds, neighbours, distance, barriers, axis conventions."""

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams


def test_cells_span_the_configured_grid(board: Board) -> None:
    assert board.size == 7
    assert len(list(board.cells())) == 49


def test_in_bounds_edges_and_corners(board: Board) -> None:
    assert board.in_bounds((0, 0))
    assert board.in_bounds((6, 6))
    assert not board.in_bounds((-1, 0))
    assert not board.in_bounds((7, 0))
    assert not board.in_bounds((0, 7))


def test_manhattan_distance() -> None:
    assert Board.manhattan((0, 0), (3, 4)) == 7
    assert Board.manhattan((2, 2), (2, 2)) == 0


def test_neighbours_exclude_off_board_cells(board: Board) -> None:
    assert set(board.neighbours((0, 0))) == {(1, 0), (0, 1)}
    assert len(set(board.neighbours((3, 3)))) == 4


def test_neighbours_exclude_barriers(params: GameParams) -> None:
    blocked = Board(params, barriers={(1, 0)})
    assert set(blocked.neighbours((0, 0))) == {(0, 1)}


def test_barrier_blocks_both_sides_and_board_stays_immutable(board: Board) -> None:
    with_barrier = board.with_barrier((2, 2))
    assert with_barrier.is_blocked((2, 2))
    assert not board.is_blocked((2, 2)), "original board must stay immutable"
    assert with_barrier.with_barrier((3, 3)).is_blocked((2, 2)), "barriers are permanent"


def test_is_open_combines_bounds_and_barriers(board: Board) -> None:
    assert board.is_open((3, 3))
    assert not board.is_open((9, 9))
    assert not board.with_barrier((3, 3)).is_open((3, 3))


def test_barrier_count_tracks_placements(board: Board) -> None:
    assert board.barrier_count == 0
    assert board.with_barrier((1, 1)).with_barrier((1, 2)).barrier_count == 2


def test_duplicate_barrier_does_not_double_count(board: Board) -> None:
    assert board.with_barrier((1, 1)).with_barrier((1, 1)).barrier_count == 1


def test_barriers_are_exposed_as_an_immutable_set(board: Board) -> None:
    """Callers (strategy search, audit log) get a snapshot they cannot mutate."""
    barriers = board.with_barrier((1, 1)).barriers
    assert barriers == frozenset({(1, 1)})
    assert isinstance(barriers, frozenset)


def test_top_left_origin_maps_north_to_decreasing_row(board: Board) -> None:
    assert board.delta_for(Move.NORTH) == (-1, 0)
    assert board.delta_for(Move.SOUTH) == (1, 0)
    assert board.delta_for(Move.EAST) == (0, 1)
    assert board.delta_for(Move.WEST) == (0, -1)
    assert board.delta_for(Move.STAY) == (0, 0)


def test_bottom_left_origin_flips_the_row_axis(game_config: dict) -> None:
    game_config["board_and_agents"]["axis_origin_corner"] = "bottom-left"
    flipped = Board(GameParams.from_config(game_config))
    assert flipped.delta_for(Move.NORTH) == (1, 0)
    assert flipped.delta_for(Move.EAST) == (0, 1)


def test_top_right_origin_flips_the_column_axis(game_config: dict) -> None:
    game_config["board_and_agents"]["axis_origin_corner"] = "top-right"
    flipped = Board(GameParams.from_config(game_config))
    assert flipped.delta_for(Move.EAST) == (0, -1)
    assert flipped.delta_for(Move.NORTH) == (-1, 0)


def test_non_zero_axis_start_index_shifts_the_coordinate_space(game_config: dict) -> None:
    game_config["board_and_agents"].update(axis_start_index=1, thief_start=[4, 4], cop_start=[1, 1])
    shifted = Board(GameParams.from_config(game_config))
    assert not shifted.in_bounds((0, 0))
    assert shifted.in_bounds((1, 1))
    assert shifted.in_bounds((7, 7))
    assert not shifted.in_bounds((8, 8))
    assert len(list(shifted.cells())) == 49
