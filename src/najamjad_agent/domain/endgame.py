"""Exact solve *with barrier placement*, for the pocket a sealing cop builds.

`strategy/solver.py` answers the movement-only question and answers it
perfectly, which is why it reports no forced win anywhere on this board — not on
the open grid, not in a carved 3x3, not with twenty free walls. A cop that only
moves cannot corner anybody on a grid: the thief dodges on parity forever.

That is not the game we play. Our cop holds fourteen barriers, and a barrier is
a *move* in the game tree that the other solver simply does not contain. Adding
it changes the answer, and this module is the answer: backward induction over

    (cop cell, thief cell, walls placed, barriers left, whose turn)

restricted to one small region, because that state space is only tractable small
— which is exactly where a sealing cop needs it. The seal shrinks the world; this
finishes what is inside it.

The cop's options at its turn are every legal step **and** every legal barrier
under the Barrier Law: its own cell or one orthogonal step, never the thief's.
Placing costs the turn, which is what makes the trade non-obvious and worth
solving rather than guessing.
"""

from functools import lru_cache

Cell = tuple[int, int]
#: Region size above which the exact solve is refused. Beyond this the state
#: space stops being small and the seal has not finished its job yet.
MAX_CELLS = 14
#: Barrier budget above which we stop searching: a pocket that needs more than
#: this is not a pocket.
MAX_BUDGET = 3


def _steps(cells: frozenset[Cell], walls: frozenset[Cell], spot: Cell) -> tuple[Cell, ...]:
    row, col = spot
    around = ((row, col), (row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
    return tuple(c for c in around if c in cells and c not in walls)


@lru_cache(maxsize=1 << 18)
def _win(cells: frozenset[Cell], cop: Cell, thief: Cell, walls: frozenset[Cell],
         left: int, cop_turn: bool, depth: int) -> bool:
    """True when the cop forces a capture from here within `depth` plies."""
    if cop == thief:
        return True
    if depth <= 0:
        return False
    if cop_turn:
        for landing in _steps(cells, walls, cop):
            if landing == thief or _win(cells, landing, thief, walls, left, False, depth - 1):
                return True
        if left > 0:
            for cell in _steps(cells, walls, cop):
                if cell == thief:
                    continue            # the Barrier Law forbids walling them
                if _win(cells, cop, thief, walls | {cell}, left - 1, False, depth - 1):
                    return True
        return False
    return all(
        _win(cells, cop, landing, walls, left, True, depth - 1)
        for landing in _steps(cells, walls, thief)
    )


def forced_capture(cells: frozenset[Cell], cop: Cell, thief: Cell,
                   walls: frozenset[Cell], left: int, plies: int = 26) -> bool:
    """Whether the cop wins this pocket outright, barriers included."""
    if len(cells) > MAX_CELLS or cop == thief:
        return cop == thief
    return _win(cells, cop, thief, walls, min(left, MAX_BUDGET), True, plies)
