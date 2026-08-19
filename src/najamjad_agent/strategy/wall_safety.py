"""Safety that accounts for the wall the cop has not placed yet.

`solver.safe_landings` answers exactly one question — can a cop that only
*moves* force a capture — and it answers it perfectly. It has no barrier moves
in its state space, which is why on this board it reports no forced win from any
region at all, a 3x3 included: without a wall the thief simply dodges on parity.

The thief has been filtering its candidate moves through that oracle and calling
the survivors "provably safe". Against a cop holding fourteen barriers they are
not. A landing with two exits is one placement from a cell with one, and one
more from none, and the oracle cannot see either because it never places a wall.

This adds the missing ply: a landing is refused when the cop, from where it will
be standing, can place a single legal barrier that turns the position into a
forced capture. One ply, not a search — the Barrier Law only lets the cop wall
its own cell or one orthogonal step from it, so there are at most five
placements to test, and each is one cached solve.
"""

from ..domain.board import Board
from ..domain.params import Position
from .solver import cop_can_force_capture


def cop_placements(board: Board, cop: Position) -> list[Position]:
    """Every cell the Barrier Law lets the cop wall from where it stands."""
    return [cell for cell in (cop, *board.neighbours(cop)) if board.is_open(cell)]


def survives_one_wall(board: Board, cop: Position, landing: Position, walls_left: int) -> bool:
    """True when no single legal cop barrier makes `landing` a forced loss.

    `walls_left` of zero restores the old behaviour exactly, because a cop with
    an empty quota really can only move — which is the situation `solver` models
    and the one case where its answer was complete all along.
    """
    if landing == cop:
        return False
    if walls_left <= 0:
        return not cop_can_force_capture(board, cop, landing)
    if cop_can_force_capture(board, cop, landing):
        return False
    for cell in cop_placements(board, cop):
        if cell == landing:
            continue                      # the Law forbids walling our cell
        walled = board.with_barrier(cell)
        if not walled.is_open(landing):
            continue
        if cop_can_force_capture(walled, cop, landing):
            return False
    return True


def safe_landings(board: Board, cop: Position, thief: Position, walls_left: int,
                  moves: tuple[Position, ...]) -> tuple[Position, ...]:
    """The landings that survive the chase, the next wall, and simple adjacency.

    The third one is not subtle and it lost a game. `solver` reports a position
    adjacent to the cop as "not a forced win", which is true — the thief can step
    away next turn — but a thief that ends its move next to the cop is captured
    by the cop simply stepping onto it. Traced on 2026-08-18: at (0,1) with the
    cop on (0,0) our thief played STAY, and both EAST and SOUTH were open, equally
    safe by every other test, and not adjacent.

    And the two tests rank in that order, which is the half that was inverted.
    At the losing cell the wall oracle rejected **both** escapes — (0,0) and
    (0,2) are corner-ish, and one wall each turns them into a forced capture —
    while passing the adjacent STAY, so the only "survivor" was the move that
    dies immediately. But the two deaths are not the same death: adjacency loses
    *this turn*, to a cop that simply steps forward, whereas a wall-trap costs
    the cop a turn to build and then still has to close, so it is two turns away
    at the earliest and only if we walk into it. Dying later strictly dominates
    dying now, and often does not happen at all.

    So: clear and wall-safe, else clear, else wall-safe, else whatever is legal.
    Each fallback matters — in a pocket every square may be adjacent, and
    returning nothing there would drop the caller into its blind policy at the
    exact moment it needs the ranking it already has.
    """
    survivors = tuple(m for m in moves if survives_one_wall(board, cop, m, walls_left))
    clear = tuple(m for m in moves if Board.manhattan(m, cop) > 1)
    return (tuple(m for m in clear if m in survivors) or clear or survivors or moves)
