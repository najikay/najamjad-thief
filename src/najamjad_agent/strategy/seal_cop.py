"""The cop that shrinks the board instead of chasing across it.

Pursuit alone cannot force a capture on an open 7x7 — the thief moves whenever
we do, and ADR-021 records the standoff that follows: against MOAAMOHA on
2026-08-17 our pursuit cop held the thief at manhattan distance 2 for
twenty-seven consecutive steps and finished the mini-game empty-handed. Distance
was never the problem. Space was.

So this one spends barriers on *structure* rather than on whichever neighbouring
cell happens to remove an escape route this turn:

    1. commit to the middle column as the cut, and to a gate in it
    2. walk our own side of it, walling the column as we pass
    3. step through the gate into the thief's half and wall it behind us
    4. we are now alone with the thief in a 7x3 — wall a row across it
    5. inside the pocket, hand back to ordinary pursuit, which converts

Three commitments, and each was a bug before it was a rule. **The gate is fixed
once**, because recomputing "leave the last cell open" every turn walked the gate
along the column until all seven cells were walled and the cop had sealed itself
away from the thief. **The row is fixed once**, for the same reason: the thief
moves, the best row changes, and a cop that re-picks each turn walls one cell of
row 2 and one of row 4 — two half-cuts that seal nothing. And **a cut is only
ever taken with the thief on our own side of it**: the inverted test walled the
row while the thief stood beyond it, sealing the quarry *away* from us, which
throws a won position.
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import confident_peak
from .cop_brain import CopBrain
from .territory import component

#: The middle column and row of the agreed 7x7 board.
CUT = 3
#: Hand back to pursuit once the thief's own region is this small. The exact win
#: table this plan is priced from says **width decides, not area**: a cop with a
#: barrier in hand forces a capture on any region three or fewer cells wide —
#: 2xN and 3x3 on one barrier, 3x4 and 3x5 on two — and fails on 4x4 at every
#: budget it can spare. Fifteen cells fall, sixteen hold. Nine is the 3x3 corner
#: of that boundary and the shape this plan actually delivers.
POCKET = 9
#: And the table's other half: the pocket is only won with barriers still in
#: hand. Below this, shrinking further is worth more than chasing inside it.
POCKET_RESERVE = 2
#: What the whole plan costs: six column cells, the gate, three row cells. We
#: hold fourteen, so the reserve above is affordable by construction.
SEAL_BUDGET = 10


@dataclass
class SealCop(CopBrain):
    """Halve the board, halve the half, then chase inside the remainder."""

    gate: Position | None = field(default=None, init=False, repr=False)
    lane: int | None = field(default=None, init=False, repr=False)
    row: int | None = field(default=None, init=False, repr=False)
    crossed: bool = field(default=False, init=False, repr=False)
    gate_shut: bool = field(default=False, init=False, repr=False)

    # ------------------------------------------------------------------ reading
    def _read(self, facts: Any) -> tuple[Board, Position | None, int, Position]:
        board = self._board(facts)
        belief = dict(getattr(facts, "belief", {}) or {})
        return (board, confident_peak(belief), int(getattr(facts, "barriers_left", 0) or 0),
                getattr(facts, "own_position", (0, 0)))

    def _commit(self, board: Board, thief: Position) -> None:
        """Fix the gate and the lane once, from where the thief was first seen."""
        if self.gate is not None:
            return
        far = 1 if thief[1] > CUT else -1
        self.lane = CUT - far
        # The gate goes at the end of the column furthest from the thief, so it
        # cannot slip round behind us while we are still building.
        self.gate = (board.size - 1, CUT) if thief[0] <= CUT else (0, CUT)

    def _settled(self, board: Board, thief: Position, left: int) -> bool:
        """True once the region is small enough *and* we still hold the reserve.

        Both halves of the table's condition. A pocket reached with an empty
        quota is not the won position the table describes, so the plan keeps
        cutting rather than handing a spent cop an unwinnable 3x3.
        """
        return len(component(board, thief)) <= POCKET and left >= POCKET_RESERVE

    # ------------------------------------------------------------------ targets
    def _column_open(self, board: Board) -> list[Position]:
        """Every cut-column cell still open, gate excluded — the plan's true state.

        **The thief's cell counts as unfinished.** It used to be filtered out
        here, so a thief standing in the gap made the column read as complete:
        the plan advanced to the row cut with rows 5 and 6 still open, the wall
        sealed nothing, and the cop wandered the last fifteen turns with six
        barriers unspent. Traced turn by turn on 2026-08-18.
        """
        rows = range(board.size - 1, -1, -1) if self.gate and self.gate[0] == 0 else range(board.size)
        return [(r, CUT) for r in rows if (r, CUT) != self.gate and board.is_open((r, CUT))]

    def _column(self, board: Board, thief: Position) -> list[Position]:
        """Column cells we may place on *this* turn — the thief's is not one."""
        return [cell for cell in self._column_open(board) if cell != thief]

    def _pick_row(self, here: Position, thief: Position, size: int,
                  region: set[Position] | None = None) -> int | None:
        """The row that best halves the region, with the thief still on our side.

        Two conditions, and the second is the one that was wrong. A cut must
        leave the thief shut in **with** us — sealing the quarry away throws the
        game, and the same-side test has guarded that since this was written.
        But among the legal rows it took the *first* it found rather than the
        best, and the order it searched put the useful cuts last: traced against
        a room-seeking thief, cop at (4,4) and thief at (0,6) ruled out rows 3, 2
        and 1 as separating, so it settled on row 5 and left the two of us in
        fifteen cells instead of nine. Fifteen is not a pocket, the plan had
        nothing further to say, and the last ten turns were spent chasing with
        four barriers in hand.

        So: score every legal row by the size of the side we would share, and
        take the smallest. The cut is symmetric in the two halves, which is the
        point — whichever half the thief flees to is the half we halve next.
        """
        rows = [r for r in range(size) if r not in (here[0], thief[0])
                and (here[0] > r) == (thief[0] > r)]
        if not rows:
            return None
        if region is None:
            return min(rows, key=lambda r: abs(r - CUT))
        # Among the rows that keep us on the thief's side, the one leaving it
        # least room. Cutting from the far side and walking over first was
        # measured on 2026-08-18 and cost a capture: the cop crosses, the thief
        # crosses back, and the turns are gone. The same-side constraint stays.
        return min(rows, key=lambda r: (sum(1 for c in region
                                            if (c[0] > r) == (thief[0] > r)), abs(r - CUT)))

    def _row_cells(self, board: Board, here: Position, thief: Position) -> list[Position]:
        """The cells that halve our own half, chosen once and then honoured.

        Halving twice and stopping is what the trace showed on 2026-08-18: the
        column closed on turn 17 and took the region from 43 cells to 21, the row
        finished on turn 24 and took it to 15, and the plan then had nothing left
        to say. Cutting *again* from there was measured and made things worse —
        it costs the turns that convert, and a random walker that was captured on
        step 27 escaped instead. Two cuts and then finish.
        """
        region = set(component(board, thief))
        # **Cutting a third time was measured and is off.** The idea is right —
        # whichever half it flees to is the half to halve next — but each extra
        # cut costs the turns that convert: re-cutting took a random walker from
        # a capture on step 27 to an escape, and still did not catch the
        # room-seeker. Two cuts and finish, until the squeeze is cheap enough to
        # afford a third.
        if self.row is None:
            self.row = self._pick_row(here, thief, board.size, region)
        if self.row is None:
            return []
        side = [c for c in range(board.size) if (c > CUT) == (thief[1] > CUT) and c != CUT]
        return [(self.row, c) for c in side
                if board.is_open((self.row, c)) and (self.row, c) != thief]

    # ------------------------------------------------------------------ helpers
    def _may_wall(self, board: Board, here: Position, cell: Position, thief: Position,
                  together: bool, gate_ok: bool = False) -> bool:
        if cell == self.gate and not gate_ok:
            return False
        if cell != here and cell not in board.neighbours(here):
            return False
        if not board.is_open(cell) or cell in (thief, here):
            return False
        walled = board.with_barrier(cell)
        if not walled.neighbours(here):
            return False
        return thief in component(walled, here) if together else True

    def _step(self, facts: Any, board: Board, here: Position, target: Position,
              keep: Position | None = None, avoid: tuple[Position, ...] = ()) -> Move | None:
        """Walk toward `target`, never landing on a cell the plan still needs.

        `avoid` is not a refinement. `_may_wall` refuses `cell == here` — a cop
        cannot wall the square it is standing on — so a cop that walks onto a
        cut cell can *never* place there, and the column stops one cell short
        forever. Traced 2026-08-18 against our own thief: the cop stepped onto
        (5,3) at turn 12 with (4,3) and (5,3) still open, and spent the next
        twenty-three turns chasing at distance 1 with four walls down, ten in
        hand and the cut unfinished. The board never dropped below 45 cells.
        """
        best, key = None, None
        for move in sorted(getattr(facts, "legal", ()), key=lambda m: m.value):
            dr, dc = board.delta_for(move)
            land = (here[0] + dr, here[1] + dc)
            if land in avoid or not board.is_open(land):
                continue
            if keep is not None and keep not in component(board, land):
                continue
            score = (Board.manhattan(land, target), move.value)
            if key is None or score < key:
                best, key = move, score
        return best

    # -------------------------------------------------------------- decisions
    def pick_barrier(self, facts: Any) -> Position | None:
        """Wall the plan, or nothing — never an opportunistic neighbour.

        **A capture on offer outranks the plan.** Placing costs the turn, so
        walling while standing next to the quarry trades a win for a wall. The
        seal is how we manufacture a capture when none is offered; it is not a
        reason to decline one. Worth 10 of 58 archived lines.
        """
        if self.capture_step_available(facts):
            return None
        board, thief, left, here = self._read(facts)
        if thief is None or left <= 0 or self._settled(board, thief, left):
            return super().pick_barrier(facts)
        self._commit(board, thief)
        same = (here[1] > CUT) == (thief[1] > CUT)
        if not self.crossed:
            for cell in self._column(board, thief):
                if self._may_wall(board, here, cell, thief, together=False):
                    return cell
            return None
        gate = self.gate
        shutting = not self.gate_shut and gate is not None and same and board.is_open(gate)
        if shutting and gate is not None and self._may_wall(board, here, gate, thief, True, True):
            self.gate_shut = True
            return gate
        for cell in self._row_cells(board, here, thief):
            if self._may_wall(board, here, cell, thief, together=True):
                return cell
        return None

    def pick_move(self, facts: Any) -> Move:
        """Take a capture if one is there; otherwise walk the plan."""
        if self.capture_step_available(facts):
            return super().pick_move(facts)
        board, thief, left, here = self._read(facts)
        if thief is None or self._settled(board, thief, left):
            return super().pick_move(facts)
        self._commit(board, thief)
        same = (here[1] > CUT) == (thief[1] > CUT)
        if not self.crossed:
            todo = self._column(board, thief)
            if self._column_open(board) and not todo:
                # Only the thief's own cell is left: hold the line rather than
                # declaring the cut finished. It has to step off eventually.
                move = self._step(facts, board, here, self._column_open(board)[0])
                return move or super().pick_move(facts)
            if todo:
                target = (todo[0][0], self.lane) if self.lane is not None else todo[0]
                move = self._step(facts, board, here, target if board.is_open(target) else todo[0],
                                  avoid=tuple(todo))
                return move or self._step(facts, board, here, target) or super().pick_move(facts)
            if self.gate and board.is_open(self.gate) and not (here == self.gate or same):
                move = self._step(facts, board, here, self.gate)
                return move or super().pick_move(facts)
            self.crossed = True
        # **Shut the gate before cutting the row.** The column is only a wall
        # once its last cell is closed: with the gate open both halves stay one
        # region, so a row cut isolates nothing and the barriers spent on it are
        # wasted. Traced 2026-08-18 — six column walls by turn 13, three row
        # walls by turn 19, and the gate still open at turn 25 with the thief
        # long gone. So if the quarry is on our side and the gate is open, walk
        # to the gate and close it first; the row comes after.
        gate = self.gate
        walk_to_gate = (gate is not None and not self.gate_shut and same
                        and board.is_open(gate) and here != gate
                        and gate not in board.neighbours(here))
        if walk_to_gate and gate is not None:
            move = self._step(facts, board, here, gate, keep=thief)
            if move:
                return move
        todo = self._row_cells(board, here, thief)
        if todo:
            move = (self._step(facts, board, here, todo[0], keep=thief, avoid=tuple(todo))
                    or self._step(facts, board, here, todo[0], keep=thief))
            if move:
                return move
        return super().pick_move(facts)
