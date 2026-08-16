"""Shared strategy scaffolding for both brains.

A brain sees only what a peer legitimately knows: its own position, the belief
grid over the opponent, the scent it has absorbed, and the legal moves. It never
sees the opponent's true cell — the orchestrator does not have it either.

Every brain output passes the orchestrator's legality filter, so a bug here
costs us a bad move, never a technical loss.
"""

from collections.abc import Iterable

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position

#: How many times the uniform share the peak must hold before a belief is
#: treated as naming a cell. Lifted from `ThiefBrain._cop_cell`, where the check
#: was written after a re-baseline caught the thief striding into a cop two
#: cells away on step 1 — the belief was uniform, `max()` returned an arbitrary
#: cell, and an arbitrary cell reported as certain is the confidently-wrong
#: failure both roles have to avoid.
CONFIDENT_SHARE = 4.0


def confident_peak(belief: dict[Position, float]) -> Position | None:
    """The cell the belief names, or None when it names none.

    Shared by both roles because both have been bitten by the same thing: the
    thief walked into a cop it could not actually locate, and the cop counted a
    flat belief as eight turns of a stalled chase and spent barriers on it.

    The cap at a half matters as much as the multiple: `CONFIDENT_SHARE /
    len(belief)` alone demands more than all the mass when the belief covers
    only a cell or two, so a *certain* localisation would be rejected as
    unreliable.
    """
    if not belief:
        return None
    total = sum(belief.values())
    if total <= 0:
        return None
    peak = max(belief, key=lambda cell: belief[cell])
    floor = min(CONFIDENT_SHARE / len(belief), 0.5)
    return peak if belief[peak] / total >= floor else None


def expected_distance(belief: dict[Position, float], cell: Position) -> float:
    """Belief-weighted Manhattan distance from `cell` to the opponent.

    Using the whole distribution rather than its peak matters when belief is
    spread: chasing the single most likely cell can walk us away from a large
    cluster of nearly-as-likely ones.
    """
    total = sum(belief.values())
    if total <= 0.0:
        return 0.0
    return sum(
        probability * (abs(cell[0] - target[0]) + abs(cell[1] - target[1]))
        for target, probability in belief.items()
    ) / total


def reachable_within(board: Board, origin: Position, radius: int) -> set[Position]:
    """Cells reachable in `radius` steps, respecting barriers and edges."""
    frontier = {origin}
    seen = {origin}
    for _ in range(max(0, radius)):
        nxt: set[Position] = set()
        for cell in frontier:
            for neighbour in board.neighbours(cell):
                if neighbour not in seen:
                    seen.add(neighbour)
                    nxt.add(neighbour)
        frontier = nxt
        if not frontier:
            break
    return seen


def escape_routes(board: Board, cell: Position) -> int:
    """How many open neighbours a cell has — its breathing room.

    The single most useful scalar in the game: a thief in a cell with one exit
    is nearly caught, and a cop that reduces this number is winning even when
    the distance has not changed.
    """
    return len(board.neighbours(cell))


def move_towards(board: Board, origin: Position, target: Position, legal: Iterable[Move]) -> Move:
    """The legal move that most reduces distance to `target`."""
    options = list(legal)
    if not options:
        return Move.STAY
    return min(
        options,
        key=lambda move: (
            _distance_after(board, origin, move, target),
            move.value,
        ),
    )


def move_away(board: Board, origin: Position, target: Position, legal: Iterable[Move]) -> Move:
    """The legal move that most increases distance from `target`."""
    options = list(legal)
    if not options:
        return Move.STAY
    return max(
        options,
        key=lambda move: (
            _distance_after(board, origin, move, target),
            -ord(move.value[0]),
        ),
    )


def _distance_after(board: Board, origin: Position, move: Move, target: Position) -> int:
    """Manhattan distance to `target` after applying `move`."""
    row_delta, col_delta = board.delta_for(move)
    landing = (origin[0] + row_delta, origin[1] + col_delta)
    return Board.manhattan(landing, target)


def apply(board: Board, origin: Position, move: Move) -> Position:
    """Where `move` lands, without validation (callers filter legality)."""
    row_delta, col_delta = board.delta_for(move)
    return (origin[0] + row_delta, origin[1] + col_delta)
