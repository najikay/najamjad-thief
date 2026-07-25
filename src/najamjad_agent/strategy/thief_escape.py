"""Measuring how trapped a cell is — the thief's core spatial judgement.

Distance from the cop is the obvious metric and it is not enough. A corner is
far from a cop on the far side of the board right up until it becomes a coffin:
one barrier and the game is over. What actually keeps a thief alive is *room*.

Two measures, deliberately different:

* **Escape routes** — immediate open neighbours. Cheap, and the number the cop's
  barrier planner is trying to reduce.
* **Freedom** — how much of the board stays reachable within a horizon. This is
  what distinguishes "a tight spot with a way out" from "a pocket", which a
  neighbour count alone cannot see.

Both respect declared barriers, so a cop's announcement immediately reshapes the
thief's map (book rules 15-16 make those declarations truthful and public).
"""

from ..domain.board import Board
from ..domain.params import Position

# A cell with one exit is a trap waiting for a single barrier; the penalty has
# to be large enough to outweigh several steps of extra distance.
DEAD_END_PENALTY = 6.0
TIGHT_SPOT_PENALTY = 2.0


def escape_routes(board: Board, cell: Position) -> int:
    """Open orthogonal neighbours — the exits a cop must close."""
    return len(board.neighbours(cell))


def freedom(board: Board, cell: Position, horizon: int = 3) -> int:
    """How many cells remain reachable from `cell` within `horizon` steps.

    A flood fill rather than a neighbour count, because being one step from a
    dead end is very different from being one step from open board.
    """
    seen = {cell}
    frontier = [cell]
    for _ in range(max(0, horizon)):
        nxt: list[Position] = []
        for current in frontier:
            for neighbour in board.neighbours(current):
                if neighbour not in seen:
                    seen.add(neighbour)
                    nxt.append(neighbour)
        frontier = nxt
        if not frontier:
            break
    return len(seen)


def is_dead_end(board: Board, cell: Position) -> bool:
    """True when a single barrier could seal this cell entirely."""
    return escape_routes(board, cell) <= 1


def trap_penalty(board: Board, cell: Position) -> float:
    """How much to distrust a cell for its lack of room."""
    routes = escape_routes(board, cell)
    if routes == 0:
        return DEAD_END_PENALTY * 2
    if routes == 1:
        return DEAD_END_PENALTY
    if routes == 2:
        return TIGHT_SPOT_PENALTY
    return 0.0


def corridor_risk(board: Board, cell: Position, horizon: int = 3) -> float:
    """Fraction of the local horizon that is *not* reachable from `cell`.

    Near 0 in open board, near 1 in a pocket. Normalising by the horizon keeps
    the number comparable between board sizes, since board size is negotiable.
    """
    reachable = freedom(board, cell, horizon)
    ideal = min(len(list(board.cells())), 1 + 2 * horizon * (horizon + 1))
    if ideal <= 1:
        return 0.0
    return max(0.0, 1.0 - (reachable - 1) / (ideal - 1))
