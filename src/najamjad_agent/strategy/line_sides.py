"""Which side of a forming fence line survives — the cop's.

A sealing cop may not complete a cut that separates it from the thief: the
plan self-checks and rebuilds (`seal_cop.pick_barrier`), so the side holding
the cop can never be sealed shut, while the far side is precisely the room
the cut is about to confiscate. Both 29-step losses to the halving cop had
the same silhouette — the thief fled *away* from the cop through the gaps of
a row being walled, and the walls closed behind it, with the whole left board
reachable through an open gate the entire game. Fleeing across a forming line
feels safe by every distance measure and is the one move the plan cannot
punish us for refusing: on the cop's side, the cut lands on an empty half and
the walls are wasted.

Split from `thief_safety` for the file budget; `choose` is the only caller.
"""

from __future__ import annotations

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import apply
from .territory import component, fence_gaps


def cop_side_of_the_line(
    board: Board,
    origin: Position,
    cop: Position,
    candidates: tuple[Move, ...],
    remaining: int,
) -> tuple[Move, ...]:
    """The candidate moves that end on the cop's side of a fence being built.

    Input: the live board, our cell, the cop's, the shortlisted moves, and the
    cop's remaining barrier quota.
    Output: the subset landing on the cop's side of the busiest wall line (or
    on the line itself, since an occupied cell cannot be walled); empty when
    there is no completable line to take a side of.
    Setup: none.

    The side is read off the board the cop is trying to reach: every gap of
    the line walled at once, then one component holds the cop and the other is
    the room the cut confiscates. A line the quota can no longer finish is no
    threat and returns empty rather than steering anything.
    """
    gaps = fence_gaps(board, cop)
    if not gaps or len(gaps) > remaining or cop in gaps:
        return ()
    closed = board
    for gap in gaps:
        if gap != origin:
            closed = closed.with_barrier(gap)
    cop_side = component(closed, cop)
    kept = []
    for move in candidates:
        landing = apply(board, origin, move)
        if landing in gaps or landing in cop_side:
            kept.append(move)
    return tuple(kept)
