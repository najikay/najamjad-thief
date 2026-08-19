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


#: One side of a split cell in `seal_cost`'s flow network: (cell, "in"|"out"),
#: plus a sink keyed on a cell no board can hold.
_Node = tuple[Position, str]
#: Cells further than this from a landing count as "the open board" for the
#: purposes of `seal_cost`. Four is a whole barrier budget's worth of walking:
#: nearer than that and a pocket is not really a pocket.
FAR_ENOUGH = 4
#: Above this a cell is not sealable in any practical sense, so the exact value
#: stops mattering and the search can stop early.
SEAL_CAP = 5


def seal_cost(board: Board, cell: Position, far: int = FAR_ENOUGH) -> int:
    """How many barriers it would take to cut `cell` off from the open board.

    The min vertex cut between `cell` and everything `far` steps away, by
    Menger's theorem the same as the number of vertex-disjoint escape routes.
    A corner is 2, an edge cell 3, an interior cell 4 — and a cell inside a
    half-built fence is whatever the fence has left open, which is the number
    that matters and the one no other key here measures.

    This exists because of a real loss. Against MOAAMOHA on 2026-08-16 our thief
    stepped to [6,6], a corner with two exits, while their cop stood adjacent
    holding eleven barriers. It walled [6,5] and [5,6] on consecutive turns and
    we were immobilised on step 14 having conceded the game. Every other key in
    `thief_safety.rank` was blind to it: the room keys saw a full-sized
    component because the walls had not been placed *yet*, and the exit count
    saturates at three so a corner and a hall scored the same.

    Vertex capacities via node splitting, then Edmonds-Karp. The board is 49
    cells, so this is microseconds and exact; an approximation here would be
    false economy.
    """
    if not board.is_open(cell):
        return 0
    distances = distances_from(board, cell)
    sinks = {spot for spot, gap in distances.items() if gap >= far and board.is_open(spot)}
    if not sinks:
        return 0
    sink: _Node = ((-1, -1), "sink")
    capacity: dict[_Node, dict[_Node, int]] = {}

    def add(source: _Node, target: _Node, amount: int) -> None:
        capacity.setdefault(source, {})[target] = amount
        capacity.setdefault(target, {}).setdefault(source, 0)

    big = SEAL_CAP + 1
    for spot in distances:
        if not board.is_open(spot):
            continue
        add((spot, "in"), (spot, "out"), big if spot == cell or spot in sinks else 1)
        for neighbour in board.neighbours(spot):
            add((spot, "out"), (neighbour, "in"), big)
    source: _Node = (cell, "out")
    for spot in sinks:
        add((spot, "out"), sink, big)
    flow = 0
    while flow < SEAL_CAP:
        parents: dict[_Node, _Node | None] = {source: None}
        queue: list[_Node] = [source]
        while queue and sink not in parents:
            node = queue.pop(0)
            for nxt, left in capacity.get(node, {}).items():
                if left > 0 and nxt not in parents:
                    parents[nxt] = node
                    queue.append(nxt)
        if sink not in parents:
            break
        step, node = big, sink
        while (previous := parents[node]) is not None:
            step = min(step, capacity[previous][node])
            node = previous
        node = sink
        while (previous := parents[node]) is not None:
            capacity[previous][node] -= step
            capacity[node][previous] += step
            node = previous
        flow += step
    return min(flow, SEAL_CAP)


#: The smallest square that is not a forced loss. The exact win table says a cop
#: holding barriers forces a capture on any region three or fewer cells wide —
#: 2xN and 3x3 with one barrier in hand, 3x4 and 3x5 with two — and fails on 4x4
#: at every budget it can spare. Width, not area, is the boundary: 3x5 has
#: fifteen cells and falls, 4x4 has sixteen and holds.
FREE_SQUARE = 4


def keeps_a_free_square(board: Board, cell: Position, cop: Position | None = None,
                        size: int = FREE_SQUARE) -> bool:
    """Whether `cell` can still reach an all-open `size` x `size` block.

    The thief's invariant, straight off the forced-win table: hold one of these
    and no cop plan in the table wins, because every winning pocket is narrower
    than this and the cop can only win a pocket it can build. Lose it and the
    game becomes a question of how long the walls take.

    Reachability *before the cop*, not mere connectivity — and that distinction
    is the whole value. Measured on the real losses: at the fatal move the board
    still held plenty of open 4x4s, every one of them on the cop's side of us.
    A square we cannot reach first is a square we do not have.
    """
    room = component(board, cell)
    if len(room) < size * size:
        return False
    if cop is not None:
        ours = distances_from(board, cell)
        theirs = distances_from(board, cop)
        room = {spot for spot in room if ours.get(spot, UNREACHABLE) < theirs.get(spot, UNREACHABLE)}
    for row in range(board.size - size + 1):
        for col in range(board.size - size + 1):
            block = [(row + dr, col + dc) for dr in range(size) for dc in range(size)]
            if all(spot in room for spot in block):
                return True
    return False


def room_we_reach_first(board: Board, cell: Position, cop: Position) -> int:
    """Cells we get to before the cop does — the room that is actually ours.

    The graded fallback behind `keeps_a_free_square`. Late in a game the answer
    to "can I still keep a 4x4?" is often no for every move, and an all-or-
    nothing filter then hands the choice back to keys that do not understand
    walls at all. That is how the last loss in the archive happened: six
    barriers down, every option failing the square test, and the ranking walked
    into the corner being sealed on step 32 of 35.
    """
    ours = distances_from(board, cell)
    theirs = distances_from(board, cop)
    return sum(1 for spot, gap in ours.items() if gap < theirs.get(spot, UNREACHABLE))


#: Collinear walls before we call it a fence under construction. Two is enough:
#: a cop does not place two walls in one line by accident, and waiting for three
#: is waiting one turn too long.
FENCE_WALLS = 2


def fence_gaps(board: Board, cop: Position) -> list[Position]:
    """Open cells on the straight line the cop is most plainly walling.

    The counter to a sealing cop, and it is a rule rather than a heuristic: the
    Barrier Law lets the cop wall its own cell or one step from it, **never the
    cell the thief is standing on**. So a thief that stands in the gap of an
    unfinished fence cannot be walled around — the cop must either abandon the
    line or come and take us, and coming costs it the turns the fence needed.

    Returns the gaps of the busiest line, furthest from the cop first, so the
    caller can stand in the one that is also safe to stand in.
    """
    rows: dict[int, int] = {}
    cols: dict[int, int] = {}
    for cell in board.cells():
        if not board.is_open(cell):
            rows[cell[0]] = rows.get(cell[0], 0) + 1
            cols[cell[1]] = cols.get(cell[1], 0) + 1
    # `-1` rather than `None` for the empty board: the count beside it is 0, so
    # the guard below returns before the index is read, and keeping it an `int`
    # keeps a `Position` a pair of ints all the way out of here.
    best_row = max(rows.items(), key=lambda kv: kv[1], default=(-1, 0))
    best_col = max(cols.items(), key=lambda kv: kv[1], default=(-1, 0))
    if max(best_row[1], best_col[1]) < FENCE_WALLS:
        return []
    if best_col[1] >= best_row[1]:
        line = [(r, best_col[0]) for r in range(board.size)]
    else:
        line = [(best_row[0], c) for c in range(board.size)]
    gaps = [cell for cell in line if board.is_open(cell)]
    return sorted(gaps, key=lambda cell: -Board.manhattan(cell, cop))


def sealing_cells(board: Board, cell: Position, far: int = FAR_ENOUGH) -> set[Position]:
    """The cells a cop would have to wall to seal `cell` off — whatever the shape.

    The general form of fence-blocking, and the reason a straight-line detector
    is not enough: the seal that beat us against MOAAMOHA was `(4,6)`, `(6,5)`,
    `(5,6)` — an L around a corner, sharing neither row nor column. A diagonal
    staircase shares neither either, and on this board a diagonal is a *complete*
    cut, since one orthogonal step changes `r + c` by exactly one.

    So the fence is not a line, it is a **cut**, and `seal_cost`'s flow network
    already knows exactly which cells form it: the saturated ones on the minimum
    cut. Standing on any of them is the block, because the Barrier Law forbids
    walling the cell the thief occupies.

    Returns the empty set when the cut is wider than a cop could finish, since
    there is then nothing to block and the thief should be running instead.
    """
    if not board.is_open(cell):
        return set()
    reachable = distances_from(board, cell)
    sinks = {spot for spot, gap in reachable.items() if gap >= far and board.is_open(spot)}
    if not sinks:
        return set()
    cut: set[Position] = set()
    for spot, gap in reachable.items():
        if spot == cell or spot in sinks or not board.is_open(spot) or gap >= SEAL_CAP:
            continue
        # A cell is on some minimum cut when walling it strictly cheapens the
        # seal — exactly the cells a fence is made of.
        if seal_cost(board.with_barrier(spot), cell, far) < seal_cost(board, cell, far):
            cut.add(spot)
    return cut if len(cut) <= SEAL_CAP else set()
