"""Who owns which ground — graph distance, components, and cut cells.

Manhattan distance is the wrong ruler once barriers exist: two cells one apart
on the grid can be twenty apart on the board, and a thief that trusts the
straight line walks into a wall it could see. Everything here works on the
*graph*, so a declared barrier changes the answer immediately.

Three measures, each earning its keep separately:

* **`distances_from`** — true step counts by breadth-first search. The thief's
  safety rule is expressed in these, not in Manhattan.
* **`component`** — the cells still mutually reachable. This is what the cop's
  barriers actually attack, and what "room" should have meant all along: a
  neighbour count cannot tell a tight spot from a sealed pocket.
* **`cut_cells`** — articulation points, whose removal would split the
  component in two. A thief must not stand behind one; a cop should barrier
  them. `thief_escape.trap_penalty` approximates this with a neighbour count
  and only fires at two exits or fewer, which on a 7x7 board is a move too
  late.
"""

from __future__ import annotations

from ..domain.board import Board
from ..domain.params import Position

UNREACHABLE = 10**6


def distances_from(board: Board, origin: Position) -> dict[Position, int]:
    """Step counts from `origin` to every cell it can reach, barriers respected."""
    seen: dict[Position, int] = {origin: 0}
    frontier = [origin]
    while frontier:
        nxt: list[Position] = []
        for cell in frontier:
            for neighbour in board.neighbours(cell):
                if neighbour not in seen:
                    seen[neighbour] = seen[cell] + 1
                    nxt.append(neighbour)
        frontier = nxt
    return seen


def graph_distance(board: Board, start: Position, goal: Position) -> int:
    """Steps between two cells, or `UNREACHABLE` when a wall separates them."""
    return distances_from(board, start).get(goal, UNREACHABLE)


def component(board: Board, origin: Position) -> set[Position]:
    """Every cell mutually reachable with `origin`."""
    return set(distances_from(board, origin))


def component_size(board: Board, origin: Position) -> int:
    """How much board the occupant of `origin` still has. Higher is safer."""
    return len(distances_from(board, origin))


def cut_cells(board: Board, origin: Position) -> set[Position]:
    """Articulation points of `origin`'s component.

    Standing beyond one of these is how a thief loses to a single barrier: the
    cop walls the cut and the pocket beyond it becomes a sealed room. Computed
    by removal rather than by Hopcroft-Tarjan — the component is at most 49
    cells, so the simple version is both fast enough and obviously correct,
    and an off-by-one in a low-link index is not a bug worth risking here.
    """
    cells = component(board, origin)
    if len(cells) <= 2:
        return set()
    cuts: set[Position] = set()
    for candidate in cells:
        remaining = cells - {candidate}
        start = next(iter(remaining))
        reached = {start}
        frontier = [start]
        while frontier:
            nxt: list[Position] = []
            for cell in frontier:
                for neighbour in board.neighbours(cell):
                    if neighbour in remaining and neighbour not in reached:
                        reached.add(neighbour)
                        nxt.append(neighbour)
            frontier = nxt
        if len(reached) != len(remaining):
            cuts.add(candidate)
    return cuts
