"""The brain, not the solver: does a shut pocket actually get converted?

`test_immobilisation_is_a_win` proves the solver finds the win. This proves the
cop *acts* on it, because a correct answer nothing calls is worth nothing — and
this repo has shipped exactly that before.

Every gate between the solver and the wire is exercised here: the localisation
gate that decides whether the endgame runs at all, the capture-first ordering,
and the barrier path. The one that actually bit us was the first —
`confident_peak` refuses a flat belief, `_read` then hands `None` to everything,
and a cop standing beside a cornered thief with barriers in hand does nothing.
Against ahk-yosi on 2026-08-21 it paced [1,5]<->[1,6] for five turns and finished
on [2,6] at step 34, three windows running, holding two barriers the whole time.

So the belief here is deliberately **flat** — the hardest case, and the one that
happened.
"""

from __future__ import annotations

from types import SimpleNamespace

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.seal_cop import SealCop

PARAMS = GameParams(grid_size=7, thief_start=(3, 3), cop_start=(0, 0), max_barriers=14,
                    max_moves=35, survival_threshold=35, axis_origin_corner="top-left",
                    axis_start_index=0, move_set=("N", "S", "E", "W", "STAY"))

#: A 3x3 room in the top-left, sealed off from the rest of the board.
ROOM = [(r, c) for r in range(3) for c in range(3)]
WALLS = [(3, 0), (3, 1), (3, 2), (0, 3), (1, 3), (2, 3)]


def sealed_board() -> Board:
    """The board is immutable by design, so the walls are seeded at birth."""
    return Board(PARAMS, barriers=WALLS)


def facts_for(board: Board, cop, step: int = 26, barriers_left: int = 2):
    """A flat belief over the room — no confident peak anywhere."""
    belief = {cell: 1.0 / len(ROOM) for cell in ROOM}
    legal = [Move.STAY]
    for move in (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST):
        dr, dc = board.delta_for(move)
        land = (cop[0] + dr, cop[1] + dc)
        if 0 <= land[0] < board.size and 0 <= land[1] < board.size and board.is_open(land):
            legal.append(move)
    return SimpleNamespace(board=board, belief=belief, own_position=cop,
                           legal=tuple(legal), barriers_left=barriers_left, step=step,
                           scent={}, own_scent={}, last_hint="", role="police")


def test_an_adjacent_thief_is_taken_and_no_barrier_is_wasted() -> None:
    """A certain capture outranks the lock: it ends the game this turn."""
    board = sealed_board()
    brain = SealCop()
    brain.board_supplier = lambda: board
    # Flat belief, but the peak we hand it is an edge cell beside the centre.
    facts = facts_for(board, cop=(1, 1))
    facts.belief = {**dict.fromkeys(ROOM, 0.01), (0, 1): 0.99}

    assert brain.pick_barrier(facts) is None, "never spend a turn walling instead"
    dr, dc = board.delta_for(brain.pick_move(facts))
    assert (1 + dr, 1 + dc) == (0, 1), "step onto them"


def test_a_cornered_thief_is_walled_in_even_on_a_flat_belief() -> None:
    """The g02 case exactly: flat belief, two barriers, thief in a corner.

    Before the localisation fallback this returned None and the cop paced.
    """
    board = sealed_board()
    brain = SealCop()
    brain.board_supplier = lambda: board
    facts = facts_for(board, cop=(1, 1))
    facts.belief = {**dict.fromkeys(ROOM, 0.0), (0, 0): 0.2, (0, 1): 0.2, (1, 0): 0.2}

    barrier = brain.pick_barrier(facts)

    assert barrier is not None, "a shut pocket must never be left unconverted"
    assert barrier in {(0, 1), (1, 0)}, "wall one of the corner's two exits"


def test_it_does_not_wander_out_of_position_while_walling() -> None:
    """Placing costs the turn; drifting would undo the geometry."""
    board = sealed_board()
    brain = SealCop()
    brain.board_supplier = lambda: board
    facts = facts_for(board, cop=(1, 1))
    facts.belief = {**dict.fromkeys(ROOM, 0.0), (0, 0): 1.0}

    assert brain.pick_barrier(facts) is not None
    assert brain.pick_move(facts) is Move.STAY
