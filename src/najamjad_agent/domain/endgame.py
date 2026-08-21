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


def _escapes(cells: frozenset[Cell], walls: frozenset[Cell], spot: Cell,
             blocked: Cell) -> tuple[Cell, ...]:
    """The thief's *movement* options: orthogonal only, and never onto the cop.

    Deliberately excludes the thief's own cell, which `_steps` includes. That
    inclusion is right for the cop — standing still is a real option for it —
    and it is what made rule 47 unreachable for the thief: with STAY always
    available the thief's option list is never empty, so `all(...)` is never
    vacuous and the solver could not represent an immobilised thief at all.
    """
    row, col = spot
    around = ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
    return tuple(c for c in around
                 if c in cells and c not in walls and c != blocked)


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
    # Rule 47: a thief with no legal *move* is captured, and standing still is
    # not an escape. This is the deterministic win the whole seal exists to set
    # up — block the thief's remaining orthogonal exits, at most three of them
    # because the cop's own body covers a fourth, and it is over. The solver
    # could not see it before: it scored only `cop == thief`, so it hunted a
    # step-on capture that a dodging thief prevents forever, spent its last
    # barriers on nothing, and paced out the clock beside a thief it had already
    # cornered. ahk-yosi confirmed the same reading of 46/47 in writing on
    # 2026-08-21 and concede for themselves when it happens.
    #
    # **But the wire only pays for co-location**, so immobilised is not scored
    # as the win itself. On 2026-08-21 the bench showed this solver walling a
    # thief into a one-cell room it could never enter — `remote seal`, three
    # reacting thieves out of three. Rule 47 makes that a win only if the
    # opponent implements rule 47, the course reference does not, and
    # `endings.own_barrier_capture` refuses to claim it for exactly that
    # reason — so a plan that ends there has spent twelve walls buying a
    # survival. Instead an escape-less thief is what it mechanically is, a
    # piece that can only STAY, and the recursion goes on until the cop has
    # walked onto it: the adjacent lock still converts in one extra step, and
    # a seal the cop cannot walk into stops being called a win at all.
    escapes = _escapes(cells, walls, thief, cop)
    if not escapes:
        return _win(cells, cop, thief, walls, left, True, depth - 1)
    # Staying is legal while any move exists, so the thief may choose it and the
    # cop must beat that too — it is only *not* a rescue when nothing else is
    # left.
    return all(
        _win(cells, cop, landing, walls, left, True, depth - 1)
        for landing in (*escapes, thief)
    )


def forced_capture(cells: frozenset[Cell], cop: Cell, thief: Cell,
                   walls: frozenset[Cell], left: int, plies: int = 26) -> bool:
    """Whether the cop wins this pocket outright, barriers included."""
    if len(cells) > MAX_CELLS or cop == thief:
        return cop == thief
    return _win(cells, cop, thief, walls, min(left, MAX_BUDGET), True, plies)

def winning_action(cells: frozenset[Cell], cop: Cell, thief: Cell,
                   walls: frozenset[Cell], left: int,
                   plies: int = 26) -> tuple[str, Cell] | None:
    """The action that captures **soonest**, or None if the pocket is not won.

    Fastest, not merely winning, and that distinction is the whole point. An
    earlier version returned the first action `_win` approved, and `_steps`
    lists the cop's own square first — so `STAY` was approved every turn and
    returned every turn. The cop built a perfect 3x3 on step 26 and then stood
    still until the clock ran out: winning "within 26 plies" is preserved by
    doing nothing, because the horizon moves with you.

    So each candidate is scored by the smallest depth at which it still wins,
    and the smallest depth is taken. That is a real capture sequence, and it
    strictly decreases, so the game finishes.

    Parity: `_win` is entered with `cop_turn=True`, so after our own action the
    position is the thief's to move and every probe passes `False`.
    """
    if len(cells) > MAX_CELLS or cop not in cells:
        return None
    budget = min(left, MAX_BUDGET)
    best: tuple[int, str, Cell] | None = None
    for landing in _steps(cells, walls, cop):
        if landing == thief:
            return ("move", landing)
        for depth in range(1, plies):
            if _win(cells, landing, thief, walls, budget, False, depth):
                if best is None or depth < best[0]:
                    best = (depth, "move", landing)
                break
    for cell in _steps(cells, walls, cop) if budget > 0 else ():
        if cell == thief:
            continue                    # the Barrier Law forbids walling them
        for depth in range(1, plies):
            if _win(cells, cop, thief, walls | {cell}, budget - 1, False, depth):
                if best is None or depth < best[0]:
                    best = (depth, "wall", cell)
                break
    return (best[1], best[2]) if best else None
