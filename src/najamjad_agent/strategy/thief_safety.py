"""The thief's survival rule: stay two steps away, and keep the big room.

This replaces a weighted sum of distance, room, risk and scent that lost three
games to a scripted opponent with no LLM. The sum was not mistuned; it was
optimising the wrong thing. Maximising distance from a cop that is sweeping
means running ahead of the broom, and our thief obligingly ran into the corner
the broom was heading for — [1,6], three games out of three.

What is true instead, and it is a theorem rather than a heuristic: **one cop
cannot catch a careful thief on an open grid.** A 7x7 board is the Cartesian
product of two paths, and the cop number of a product of two trees is 2
(Maamoun and Meyniel), so a lone pursuer can always be evaded. Exact retrograde
analysis of all 2401 positions agrees: the only states the cop wins are the
ones where it already shares our cell.

So the thief does not need to be clever, it needs to be disciplined:

1. **Never end a turn within one step of the cop.** At distance two the cop
   cannot reach us next turn, so we are safe by construction. Even a corner
   works: cornered at [0,6] with the cop at [0,5], step to [1,6]; it follows to
   [1,5], step back to [0,6]. The oscillation never loses.
2. **Among safe cells, take the largest room.** Component size, not neighbour
   count — the thing barriers actually attack. This is what stops us walking
   into a pocket that a single wall seals.
3. **Never stand beyond a cut cell** while the cop can still spend barriers,
   because that is precisely the one wall that would seal us in.

Distances are graph distances, so a declared barrier reshapes the rule at once.
"""

from __future__ import annotations

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import apply
from .territory import UNREACHABLE, component_size, cut_cells, distances_from

#: Below this the cop is adjacent and can take us on its next move.
SAFE_DISTANCE = 2
#: A room smaller than this is a trap being closed, however far away the cop is.
CRAMPED_ROOM = 6


def safe_moves(
    board: Board,
    origin: Position,
    cop: Position,
    legal: tuple[Move, ...],
    reach: dict[Position, int] | None = None,
) -> tuple[Move, ...]:
    """The moves that leave us at least `SAFE_DISTANCE` from the cop.

    Input: the live board, our cell, the cop's cell, the legal moves, and
    optionally the cop's precomputed distance map.
    Output: the safe subset, or every legal move when none is safe.
    Setup: none.

    Falling back to everything rather than to nothing matters: a thief with no
    safe move still has to move, and returning an empty tuple would make the
    caller pick arbitrarily at exactly the moment care is worth most.
    """
    from_cop = distances_from(board, cop) if reach is None else reach

    def at_least(floor: int) -> tuple[Move, ...]:
        return tuple(
            move
            for move in legal
            if board.is_open(apply(board, origin, move))
            and from_cop.get(apply(board, origin, move), UNREACHABLE) >= floor
        )

    # Graded, not all-or-nothing. The first version fell straight back to every
    # legal move the moment nothing was safe, which let the ranking choose the
    # cop's own cell — a move that is never right, and it walked us into a
    # capture on step 34 of a game we were otherwise winning. Distance 1 is
    # survivable (the cop still has to guess), distance 0 is a loss by
    # definition, so they must not be pooled.
    return at_least(SAFE_DISTANCE) or at_least(1) or legal


def adversarial_room(board: Board, cell: Position, cuts: frozenset[Position]) -> int:
    """Room left at `cell` after the cop's single most damaging next barrier.

    The honest version of "do not get sealed in". An earlier attempt penalised
    *standing on* an articulation point, which is backwards and produced exactly
    the wrong move: at a leaf cell whose only exit is a cut, it preferred to sit
    in the one-exit dead end rather than step onto the choke point. Occupying a
    cut cell is fine — being stranded *behind* one is what loses.

    So the threat is measured rather than proxied: wall each neighbour in turn
    and keep the worst room we would be left with. `cuts` is a pre-filter, since
    a component with no articulation points cannot be split by one barrier at
    all, and that is the common case on an open board.
    """
    if not cuts:
        return component_size(board, cell)
    worst = component_size(board, cell)
    for neighbour in board.neighbours(cell):
        if neighbour in cuts:
            worst = min(worst, component_size(board.with_barrier(neighbour), cell))
    return worst


def rank(
    board: Board,
    origin: Position,
    move: Move,
    reach: dict[Position, int],
    cuts: frozenset[Position],
) -> tuple[int, int, int, int]:
    """Sort key for one move; larger is better.

    Room first, then distance. That order is the whole correction: the old
    policy put distance first and room second, which is what walked us into a
    far corner instead of a near hall.

    **Room is measured twice, at two scales, and it has to be.** Component size
    separates a sealed pocket from the open board. But every cell of one
    component has the *same* component size, so on an intact board that key is
    constant and the ranking silently collapses back to distance-only — which
    is the exact bug being fixed here, wearing a different hat. It preferred a
    one-exit cell to a two-exit neighbour because it was a step further from the
    cop. Escape routes discriminate inside the room; component size discriminates
    between rooms. Two existing tests caught this and were right to.

    `reach` and `cuts` are passed in rather than derived here. They depend only
    on the board and the cop, not on which move we are scoring, and computing
    them per candidate made a turn take seconds instead of milliseconds.
    """
    landing = apply(board, origin, move)
    if not board.is_open(landing):
        return (-1, -1, -1, -1)
    return (
        # Room after the cop's worst single reply, which is the room that is
        # actually ours. Equal to the plain component size once the barrier
        # budget is spent, because then the geometry is fixed.
        min(adversarial_room(board, landing, cuts), 49),
        min(component_size(board, landing), 49),
        len(board.neighbours(landing)),
        min(reach.get(landing, 0), 12),
    )


def survives_the_reply(
    board: Board, landing: Position, cop: Position, legal: tuple[Move, ...]
) -> bool:
    """Would we still have a safe move after the cop's best answer?

    The one-turn invariant is not enough on its own, and a self-play game showed
    exactly how it fails. Cornered at [0,6] with the cop at [1,5], `STAY` is
    genuinely safe — distance 2, the cop cannot reach us. It moves to [1,6], a
    barrier closes [0,5], and now every move is distance 1 or 0. Safe on one
    turn, lost on the next.

    The theorem that a lone cop cannot catch a careful thief holds on an *open*
    grid. Barriers are precisely what breaks it, so the thief has to see one
    move further than the cop's own.

    The cop's replies are its neighbours plus standing still, so at most five
    distance maps, computed once and shared across every candidate.
    """
    for reply in (cop, *board.neighbours(cop)):
        after = distances_from(board, reply)
        escapes = any(
            board.is_open(apply(board, landing, move))
            and after.get(apply(board, landing, move), UNREACHABLE) >= SAFE_DISTANCE
            for move in legal
        )
        if not escapes:
            return False
    return True


def cop_barriers_left(board: Board) -> int:
    """How many walls the cop can still place, read off the board.

    Deliberately *not* taken from `TurnFacts.barriers_left`: that field is the
    holder's own quota, and a thief's own quota is always zero — so keying the
    cut-cell guard on it disabled the guard for the only role that needs it.
    The board knows the agreed maximum and how many are already down, which is
    the same number and cannot be read from the wrong side.
    """
    return max(0, board.params.max_barriers - board.barrier_count)


def choose(
    board: Board,
    origin: Position,
    cop: Position,
    legal: tuple[Move, ...],
    barriers_left: int | None = None,
) -> tuple[Move, ...]:
    """Every move tied for best, in preference order — the caller breaks ties.

    Returning the whole tied set rather than one move is deliberate: it is what
    lets the caller randomise among *equally safe* options without ever trading
    safety for unpredictability. A scripted opponent solved our last thief
    because it played one line; it must not be able to solve this one either.

    `barriers_left` defaults to the cop's true remaining quota derived from the
    board. Pass it only to model a hypothetical.
    """
    remaining = cop_barriers_left(board) if barriers_left is None else barriers_left
    reach = distances_from(board, cop)
    candidates = safe_moves(board, origin, cop, legal, reach)
    if not candidates:
        return (Move.STAY,)
    # Prefer the moves that are still safe a turn later. Only a preference:
    # when nothing survives the reply we are already losing, and refusing to
    # move would forfeit the chance that the cop answers imperfectly.
    lasting = tuple(
        move
        for move in candidates
        if survives_the_reply(board, apply(board, origin, move), cop, legal)
    )
    candidates = lasting or candidates
    cuts = frozenset(cut_cells(board, origin)) if remaining > 0 else frozenset()
    scored = [(rank(board, origin, move, reach, cuts), move) for move in candidates]
    best = max(score for score, _ in scored)
    return tuple(move for score, move in scored if score == best)


def cramped(board: Board, cell: Position) -> bool:
    """True when the room around `cell` is small enough to be a closing trap."""
    return component_size(board, cell) < CRAMPED_ROOM
