"""The one barrier that ends it, checked every turn and owned by nobody else.

Rule 47 as both teams agreed it on 2026-08-21: a thief with no legal move is
captured, and standing still is not an escape. The cop's own body blocks one
exit, so a thief with a single remaining exit is one barrier from finished.

This is deliberately not part of the exact solver. `endgame.winning_action`
refuses unless the whole reachable component is under `MAX_CELLS`, which is the
right guard for a search over a region — and exactly wrong for this, because a
thief pinned against walls with one way out is winnable now while its component
is still most of the board. Naji watched that position sit unplayed on the
dashboard more than once; the win was never searched for because the search
declined to start.
"""

from __future__ import annotations

from ..domain.board import Board
from ..domain.endgame import MAX_CELLS
from ..domain.params import Position
from .base import confident_peak
from .territory import component


def lock_cell(board: Board, thief: Position, here: Position,
          left: int) -> Position | None:
    """The single barrier that leaves them no legal move, if there is one.

    Independent of the exact solver on purpose. `_endgame` refuses unless the
    whole reachable component is under `MAX_CELLS`, which is right for a
    search over the region — but a thief pinned against walls with one exit
    left is winnable *now*, and its component can still be most of the board
    because the pocket is not shut. So the cheapest, most certain win we have
    was invisible exactly when Naji could see it on the dashboard.

    Rule 47 as both teams agreed it on 2026-08-21: no legal move is a
    capture, and standing still is not an escape. Our own body blocks one
    exit; if exactly one other remains and the Barrier Law lets us reach it —
    our cell or one orthogonal step, never theirs — walling it ends the game.
    """
    if left <= 0:
        return None
    if here not in board.neighbours(thief):
        # **The cage is our body plus the wall, so the body must be a bar.**
        # Without this line "one exit besides our body" degrades, whenever we
        # stand further off, into plain "one exit" — and walling that seals a
        # room we are not part of and can never enter. The bench named it on
        # 2026-08-21: three reacting thieves out of three ended `remote seal
        # (rule 47 only)`, twelve walls spent on a position the filing layer
        # refuses to claim against a reference peer. Adjacent, the same wall
        # is a true lock: they are forced to STAY and we step onto them.
        return None
    exits = [cell for cell in board.neighbours(thief) if cell != here]
    if len(exits) != 1:
        return None
    target = exits[0]
    if target == thief:
        return None
    reachable = {here, *board.neighbours(here)}
    return target if target in reachable else None


def locate(board: Board, belief: dict[Position, float],
       here: Position) -> Position | None:
    """Where they are: the confident peak, or the best cell in a shut room.

    `confident_peak` refuses a flat belief, and it is right to on an open
    board — a cop that chases noise spends barriers on nothing, which is a
    fault this class has had. But it returns None on *any* flat belief, and
    the moment that matters most is the one where the reasoning does not
    apply: once the seal is shut we are in a room of a handful of cells with
    them, every one of which we can see, and "not confident enough" there
    means refusing to act on the only answer available.

    The cost of that refusal is total. `_read` hands None to everything —
    `_capture_now`, `_endgame`, the script — so a cop standing next to a
    cornered thief with barriers in hand does nothing at all. Against
    ahk-yosi it paced beside a thief it had already trapped, three windows
    running.

    So inside a component small enough for the exact solver, we take the
    peak. The gate keeps its whole meaning on the open board, where the
    component is the board and this never fires.
    """
    peak = confident_peak(belief)
    if peak is not None:
        return peak
    room = component(board, here)
    if not room or len(room) > MAX_CELLS:
        return None
    inside = {cell: weight for cell, weight in belief.items() if cell in room}
    if not inside or max(inside.values()) <= 0.0:
        return None
    return max(inside, key=lambda cell: inside[cell])
