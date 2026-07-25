"""Tests for the thief's spatial judgement — room, not just distance."""

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.thief_escape import (
    corridor_risk,
    escape_routes,
    freedom,
    is_dead_end,
    trap_penalty,
)
from tests.fakes.orchestration import build_state


def _board() -> Board:
    return build_state(Role.THIEF).board


def test_escape_routes_counts_open_neighbours() -> None:
    board = _board()
    assert escape_routes(board, (3, 3)) == 4
    assert escape_routes(board, (0, 0)) == 2


def test_freedom_grows_with_the_horizon() -> None:
    """A flood fill, because one step from a dead end differs from open board."""
    board = _board()
    assert freedom(board, (3, 3), 0) == 1
    assert freedom(board, (3, 3), 1) == 5
    assert freedom(board, (3, 3), 2) > freedom(board, (3, 3), 1)


def test_freedom_stops_early_when_fully_enclosed() -> None:
    board = _board().with_barrier((0, 1)).with_barrier((1, 0))
    assert freedom(board, (0, 0), 5) == 1


def test_a_negative_horizon_is_treated_as_zero() -> None:
    assert freedom(_board(), (3, 3), -2) == 1


def test_a_dead_end_is_recognised() -> None:
    """One exit means a single barrier ends the game."""
    board = _board().with_barrier((0, 1))
    assert is_dead_end(board, (0, 0))
    assert not is_dead_end(board, (3, 3))


def test_trap_penalties_scale_with_confinement() -> None:
    board = _board()
    open_ground = trap_penalty(board, (3, 3))
    tight = trap_penalty(board.with_barrier((0, 1)), (0, 0))
    sealed = trap_penalty(board.with_barrier((0, 1)).with_barrier((1, 0)), (0, 0))
    assert open_ground == 0.0
    assert 0 < trap_penalty(board, (0, 0)) < tight < sealed


def test_corridor_risk_is_low_in_the_open_and_high_in_a_pocket() -> None:
    board = _board()
    sealed = board.with_barrier((0, 1)).with_barrier((1, 0))
    assert corridor_risk(board, (3, 3)) < 0.5
    assert corridor_risk(sealed, (0, 0)) > 0.9


def test_corridor_risk_is_normalised_between_zero_and_one() -> None:
    """Board size is negotiable, so the measure must stay comparable."""
    board = _board()
    for cell in board.cells():
        assert 0.0 <= corridor_risk(board, cell) <= 1.0


def test_corridor_risk_of_a_zero_horizon_is_zero() -> None:
    assert corridor_risk(_board(), (3, 3), horizon=0) == 0.0
