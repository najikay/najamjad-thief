"""Shared domain fixtures: the Appendix F default contract, params, and board.

Every domain test starts from the book's sample contract (7x7, thief centre,
cop corner, 14 barriers, 35 steps) so that a drift away from Appendix F breaks
tests loudly rather than silently changing the game we play.
"""

from copy import deepcopy

import pytest

from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams

BASE_CONFIG: dict = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}


@pytest.fixture()
def game_config() -> dict:
    """A fresh, mutable copy of the default agreed contract."""
    return deepcopy(BASE_CONFIG)


@pytest.fixture()
def params(game_config: dict) -> GameParams:
    """Validated parameters for the default contract."""
    return GameParams.from_config(game_config)


@pytest.fixture()
def board(params: GameParams) -> Board:
    """An empty 7x7 board under default axis conventions."""
    return Board(params)
