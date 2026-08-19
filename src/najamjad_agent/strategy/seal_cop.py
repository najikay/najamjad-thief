"""The cop that walks a lane and walls the line beside it.

The plan is Naji's, dictated from a live board on 2026-08-18 after the previous
version sealed itself away from its own gate. It is written as an explicit
script rather than as per-turn scoring, because every failure this class has had
came from re-deciding something that should have been decided once.

**The column.** Walk column 2 from the top, walling column 3 as you pass:
stand (0,2) wall (0,3), stand (1,2) wall (1,3), ... stand (5,2) wall (5,3).
Then stand (6,2). The last cell (6,3) is the **gate**. If the thief is on the
right, step through it to (6,4) and wall (6,3) behind you; if the thief is on
the left you are already with it, so wall (6,3) from where you stand.

**The row**, mirrored, inside whichever half holds the thief. In the right half:
stand (4,4) wall (3,4), stand (4,5) wall (3,5), then stand (4,6) — and (3,6) is
this cut's gate. Thief below? Wall it from (4,6). Thief above? Step (3,6) then
(2,6) and wall (3,6) behind you. Left half is the mirror through column 3.

Either way the thief ends in a 3x3 with the cop, which the exact table calls a
forced win on a single barrier. And a thief that tries to slip through either
gate at the moment we close it is standing next to us, so we take it instead.

The two rules that make this work, and that the previous version broke:
**never wall a cell you still have to walk through**, and **never start the
second cut before the first one's gate is shut** — that is precisely how the
cop walled (2,4), cut itself off from the gate at (0,3), and stood still.
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.endgame import MAX_CELLS, winning_action
from ..domain.params import Position
from .base import confident_peak
from .cop_brain import CopBrain
from .territory import component

#: The middle column and row of the agreed 7x7 board.
CUT = 3
#: The lane we walk while walling the column: alongside it, never on it.
LANE = CUT - 1
#: Hand back once the thief's region is this small — the 3x3 the plan delivers.
POCKET = 9


@dataclass
class SealCop(CopBrain):
    """Halve the board, halve the half, then convert the 3x3."""

    script: list[tuple[Position, Position | None]] = field(default_factory=list, init=False)
    phase: str = field(default="column", init=False)

    # ------------------------------------------------------------------ script
    def _column_script(self, thief: Position) -> list[tuple[Position, Position | None]]:
        """Stand-here, wall-that, down column `LANE`. The gate is NOT in here.

        Rows 0..5 only. `(6, CUT)` is the gate and is decided when we arrive,
        not now: the thief moves while we are walling, and a crossing baked in
        at build time is a crossing planned for a board that no longer exists.
        That exact mistake sealed the gate from the left while the thief stood
        on the right, and the cop then stood on (6,2) with nowhere to go.
        """
        return [((row, LANE), (row, CUT)) for row in range(6)]

    def _gate_script(self, thief: Position) -> list[tuple[Position, Position | None]]:
        """The gate, decided on arrival from where the thief actually is."""
        if thief[1] > CUT:
            # Cross at the bottom and wall it behind us.
            return [((6, LANE), None), ((6, CUT), None), ((6, CUT + 1), (6, CUT))]
        return [((6, LANE), (6, CUT))]

    def _row_script(self, thief: Position) -> list[tuple[Position, Position | None]]:
        """The same shape, mirrored, inside the half that holds the thief."""
        right = thief[1] > CUT
        cols = [CUT + 1, CUT + 2, CUT + 3] if right else [CUT - 1, CUT - 2, CUT - 3]
        far = cols[-1]
        steps: list[tuple[Position, Position | None]] = [
            ((4, cols[0]), (CUT, cols[0])), ((4, cols[1]), (CUT, cols[1]))
        ]
        if thief[0] > CUT:
            steps += [((4, far), (CUT, far))]          # thief below: wall from here
        else:
            steps += [((4, far), None), ((CUT, far), None), ((2, far), (CUT, far))]
        return steps

    # ------------------------------------------------------------------ helpers
    def _read(self, facts: Any) -> tuple[Board, Position | None, int, Position]:
        board = self._board(facts)
        belief = dict(getattr(facts, "belief", {}) or {})
        return (board, confident_peak(belief), int(getattr(facts, "barriers_left", 0) or 0),
                getattr(facts, "own_position", (0, 0)))

    def _refill(self, board: Board, thief: Position, here: Position) -> None:
        """Move to the next phase only once the current one is genuinely spent."""
        if self.phase == "column" and not self.script:
            self.script = self._column_script(thief)
        self._advance(board, here)
        if self.script:
            return
        if self.phase == "column":
            self.phase = "gate"
            self.script = self._gate_script(thief)
        elif self.phase == "gate":
            self.phase = "row"
            self.script = self._row_script(thief)
        self._advance(board, here)

    def _advance(self, board: Board, here: Position) -> None:
        """Drop script entries already satisfied."""
        while self.script:
            stand, wall = self.script[0]
            if wall is not None and not board.is_open(wall):
                self.script.pop(0)
                continue
            if wall is None and here == stand:
                self.script.pop(0)
                continue
            break

    def _capture_now(self, facts: Any, board: Board, here: Position,
                     thief: Position) -> Move | None:
        """The move that lands exactly on the thief, or None. Never pursuit.

        `CopBrain.capture_step_available` answers a softer question — whether a
        *believed* capture is within a step, judged against a probability bar —
        and `pick_move` then handed the turn to the pursuit brain. So every turn
        the cop stood near the thief it dropped the script and chased, and the
        seal was abandoned half-built. Naji watched it happen in a live game and
        it is the single thing he has had to repeat most.

        The plan IS the strategy: the seal is how a capture is manufactured, not
        an alternative to taking one that is already there. So the only thing
        allowed to interrupt the script is a move that ends the game this turn —
        a landing on the thief's own cell — and stepping toward it is not that.
        """
        for move in getattr(facts, "legal", ()):
            row, col = board.delta_for(move)
            if (here[0] + row, here[1] + col) == thief:
                return move
        return None

    def _endgame(self, facts: Any) -> tuple[str, Position] | None:
        board, thief, left, here = self._read(facts)
        if thief is None:
            return None
        region = frozenset(component(board, thief))
        if len(region) > MAX_CELLS or here not in region:
            return None
        return winning_action(region, here, thief, frozenset(), left)

    def _step_to(self, facts: Any, board: Board, here: Position,
                 target: Position) -> Move | None:
        """Walk toward `target`, never onto a cell the script still needs walled."""
        # The square we are being sent to is exempt. A gate is both a cell we
        # walk THROUGH and a cell we wall behind us afterwards, so a blanket
        # "never step on a pending wall" rule forbids the crossing itself — the
        # cop stood on (6,2) playing STAY with the gate open beside it.
        pending = {wall for _stand, wall in self.script if wall is not None} - {target}
        best, key = None, None
        for move in sorted(getattr(facts, "legal", ()), key=lambda m: m.value):
            dr, dc = board.delta_for(move)
            land = (here[0] + dr, here[1] + dc)
            if not board.is_open(land) or land in pending:
                continue
            score = (Board.manhattan(land, target), move.value)
            if key is None or score < key:
                best, key = move, score
        return best

    # -------------------------------------------------------------- decisions
    def pick_barrier(self, facts: Any) -> Position | None:
        """Wall the script's current cell, and only from the square it names."""
        board_now, thief_now, _l, here_now = self._read(facts)
        if thief_now is not None and self._capture_now(facts, board_now, here_now, thief_now):
            return None                 # a real capture next; do not spend the turn walling
        exact = self._endgame(facts)
        if exact is not None:
            return exact[1] if exact[0] == "wall" else None
        board, thief, left, here = self._read(facts)
        if thief is None or left <= 0:
            return super().pick_barrier(facts)
        self._refill(board, thief, here)
        if not self.script:
            return super().pick_barrier(facts)
        stand, wall = self.script[0]
        if wall is None or here != stand or not board.is_open(wall) or wall == thief:
            return None
        walled = board.with_barrier(wall)
        if not walled.neighbours(here):
            return None
        self.script.pop(0)
        return wall

    def pick_move(self, facts: Any) -> Move:
        """Walk to the square the script names next."""
        board, thief, _left, here = self._read(facts)
        if thief is None:
            return super().pick_move(facts)
        taking = self._capture_now(facts, board, here, thief)
        if taking is not None:
            return taking
        exact = self._endgame(facts)
        if exact is not None and exact[0] == "move":
            for move in getattr(facts, "legal", ()):
                dr, dc = board.delta_for(move)
                if (here[0] + dr, here[1] + dc) == exact[1]:
                    return move
        self._refill(board, thief, here)
        if not self.script:
            return super().pick_move(facts)
        stand, _wall = self.script[0]
        move = self._step_to(facts, board, here, stand)
        return move or super().pick_move(facts)
