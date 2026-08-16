"""The move that lost moaamoha g03, and which brain actually made it.

2026-08-15, friendly against moaamoha, mini-game 3. Our thief sat on [6,5] for
three turns, then stepped north to [5,5] — one square from their cop on [5,4],
which stepped onto it and claimed. We lost g01 the same way.

The position is not in dispute: their cop declared it. A capture claim named
[5,4] at step 9, their step-10 scent grid peaked on [5,4], and their step-10
barrier at [6,4] put them on `[[5,4],[6,3],[6,5]]`. So this is not a sensing
failure, and the interesting question is which policy made the move.

**The full-strength thief does not make it, and the sandbagged one does.** That
is the friendly working as designed — `match_day.py warmup` arms `sandbagged`,
and the whole point of the dial is that a team we may meet again does not get to
watch our real policy. It is worth a test because the conclusion is easy to get
backwards from the outside: two captures in six mini-games look like a defect,
and the defect would be real if the full brain had chosen it.
"""

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.domain.params import GameParams
from najamjad_agent.shared.strength import SANDBAGGED
from najamjad_agent.strategy import thief_safety
from najamjad_agent.strategy.territory import distances_from
from najamjad_agent.strategy.thief_brain import ThiefBrain

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
    },
}
#: Their cop's cell at our step-11 decision, from their own declarations.
COP = (5, 4)
#: Ours, and the wall their step-10 barrier put beside us.
THIEF, WALL = (6, 5), (6, 4)
#: The set their barrier declaration named, logged as `cop.sighted`.
BARRIER_SET = (COP, (6, 3), (6, 5))


@pytest.fixture()
def board() -> Board:
    return Board(GameParams.from_config(CONFIG)).with_barrier(WALL)


@pytest.fixture()
def belief(board: Board) -> dict:
    """What we held: the cop's cell, narrowed again by the barrier declaration."""
    grid = BeliefGrid(board, start=COP)
    grid.observe_reach(BARRIER_SET, 0.85)
    return grid.as_dict()


class Facts:
    """The view the orchestrator hands a thief brain."""

    def __init__(self, board: Board, belief: dict) -> None:
        self.board = board
        self.own_position = THIEF
        self.belief = belief
        self.scent = dict.fromkeys(board.cells(), 0.0)
        self.own_scent = dict.fromkeys(board.cells(), 0.0)
        self.legal = legal_moves(board, THIEF)
        self.barriers_left = 0
        self.role = "thief"
        self.step = 11
        self.steps_remaining = 24
        self.sub_game = 3


def test_north_was_the_losing_move_and_east_was_available(board: Board) -> None:
    """The geometry first, so the rest of the file is about a real choice."""
    reach = distances_from(board, COP)

    landings = {
        move.value: reach.get(thief_safety.apply(board, THIEF, move))
        for move in legal_moves(board, THIEF)
    }

    assert landings == {"N": 1, "E": 3, "STAY": 2}, landings
    safe = thief_safety.safe_moves(board, THIEF, COP, legal_moves(board, THIEF))
    assert Move.NORTH not in safe, "distance 1 is inside the cop's reach for its next move"


def test_the_full_strength_thief_keeps_its_distance(board: Board, belief: dict) -> None:
    """`thief_safety` excludes the move; the full brain must actually use it."""
    move = ThiefBrain().pick_move(Facts(board, belief))

    assert move is Move.EAST, f"stepped {move.value} into the cop's reach"


def test_the_sandbagged_thief_is_the_one_that_walked_into_it(board: Board, belief: dict) -> None:
    """Sandbagging has to be visibly weaker or a warm-up leaks the real policy.

    Pinned to the exact position that cost a real mini-game rather than to a
    synthetic one: this is the difference the dial is *for*, and if the two
    strengths ever agree here the warm-up has stopped protecting anything.
    """
    move = ThiefBrain(strength=SANDBAGGED).pick_move(Facts(board, belief))

    assert move is Move.NORTH, "the sandbagged policy no longer reproduces the loss"
