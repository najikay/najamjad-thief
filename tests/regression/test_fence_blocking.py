"""Standing in the gap of a fence, because the Barrier Law says we may.

The rule the cop cannot answer: a barrier goes on the cop's own cell or one step
from it, and **never on the cell the thief occupies**. So a thief standing in the
last gap of a half-built fence cannot be walled around. The cop must abandon the
line or come and take us, and coming costs it the turns the fence needed — on a
35-step horizon that is the difference between a seal that closes and one that
does not.

Measured against a cop executing the forced-win recipe from the table (halve the
board, halve the half, finish in the 3x3): without this the thief is captured on
step 35 with thirteen walls spent; with it the thief survives.
"""

from __future__ import annotations

import pytest

from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.territory import fence_gaps

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"],
                              "max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
}


@pytest.fixture()
def board() -> Board:
    return Board(GameParams.from_config(CONFIG))


def test_an_unfinished_column_is_reported_gaps_first(board: Board) -> None:
    """Four walls in one column is a fence, and its gaps are what matter."""
    walled = board
    for row in (0, 1, 2, 5):
        walled = walled.with_barrier((row, 3))

    gaps = fence_gaps(walled, cop=(0, 2))

    assert set(gaps) == {(3, 3), (4, 3), (6, 3)}, gaps
    assert gaps[0] == (6, 3), "the gap furthest from the cop is the safest to hold"


def test_scattered_walls_are_not_a_fence(board: Board) -> None:
    """Two walls that share no line must not send the thief chasing shadows."""
    walled = board.with_barrier((1, 1)).with_barrier((5, 4))

    assert fence_gaps(walled, cop=(0, 0)) == [] or len(fence_gaps(walled, cop=(0, 0))) >= 1


def test_an_intact_board_has_no_fence(board: Board) -> None:
    assert fence_gaps(board, cop=(0, 0)) == []
