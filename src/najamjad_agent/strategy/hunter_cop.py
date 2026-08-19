"""Seal the board down to a pocket, then take the forced capture inside it.

The two facts this is built on are computed, not assumed:

* `strategy/solver.py` — movement only — reports **no** forced cop win anywhere
  on this board. Not on the open grid, not in a carved 3x3, not with twenty free
  walls. A cop that only steps cannot corner anybody on a grid.
* `domain/endgame.py` — the same induction **with barrier placement in the tree**
  — reports a forced win in a 3x3 holding one barrier, and in a 3x4 or a 2x7
  holding two. All of them are losses at budget zero.

So the whole cop problem is: get the thief into a region of at most fourteen
cells while still holding two barriers, and then stop guessing and play the
solved line. That is what this does, in that order, with no tunable constants:

  1. inside a pocket the endgame says is won -> play the winning move or wall
  2. otherwise, if a single legal wall creates such a pocket -> place it
  3. otherwise shrink: the wall that most reduces the thief's region
  4. otherwise close the distance

Step 3 is the only heuristic, and it is bounded: it refuses to spend below the
reserve the endgame needs, because a pocket reached with an empty quota is a
draw and this whole design turns on that number being two.
"""

from dataclasses import dataclass
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.endgame import MAX_CELLS, forced_capture
from ..domain.params import Position
from .base import confident_peak
from .seal_cop import SealCop
from .territory import component

#: Barriers kept back for the endgame. Two, because 3x4 and 2x7 need two and a
#: 3x3 needs one; arriving with fewer converts a won pocket into a stalemate.
RESERVE = 2


@dataclass
class HunterCop(SealCop):
    """Shrink until the pocket is solvable, then play the solved line."""

    def _read(self, facts: Any) -> tuple[Board, Position | None, int, Position]:
        board = self._board(facts)
        return (board, confident_peak(dict(getattr(facts, "belief", {}) or {})),
                int(getattr(facts, "barriers_left", 0) or 0),
                getattr(facts, "own_position", (0, 0)))

    def _pocket(self, board: Board, thief: Position) -> frozenset[Position]:
        return frozenset(component(board, thief))

    def _won(self, board: Board, here: Position, thief: Position, left: int) -> bool:
        pocket = self._pocket(board, thief)
        if len(pocket) > MAX_CELLS or here not in pocket:
            return False
        return forced_capture(pocket, here, thief, frozenset(), left)

    def _legal_walls(self, board: Board, here: Position, thief: Position) -> list[Position]:
        """Barrier Law placements that keep us in the same region as the thief."""
        out = []
        for cell in (here, *board.neighbours(here)):
            if not board.is_open(cell) or cell in (thief, here):
                continue
            walled = board.with_barrier(cell)
            if walled.neighbours(here) and thief in component(walled, here):
                out.append(cell)
        return out

    def pick_barrier(self, facts: Any) -> Position | None:
        board, thief, left, here = self._read(facts)
        if thief is None or left <= 0:
            return super().pick_barrier(facts)
        if self.capture_step_available(facts):
            return None
        walls = self._legal_walls(board, here, thief)
        if self._won(board, here, thief, left):
            # Inside a solved pocket a wall is only right when it is the winning
            # move; the endgame is asked, never guessed at.
            for cell in walls:
                walled = board.with_barrier(cell)
                if self._won(walled, here, thief, left - 1):
                    return cell
            return None
        making = [c for c in walls if self._won(board.with_barrier(c), here, thief, left - 1)]
        if making:
            return min(making, key=lambda c: len(component(board.with_barrier(c), thief)))
        if left <= RESERVE:
            return None                    # keep what the endgame will need
        # Greedy shrinking cannot reach a pocket and measurably costs games: a
        # single wall removes about one cell from a connected region, so
        # fourteen of them cannot take forty-nine cells down to fourteen, and
        # the turns spent trying let a random walker escape that plain pursuit
        # catches on step five. Only a structured cut gets there, so the
        # approach march is `SealCop`'s committed halving plan.
        return super().pick_barrier(facts)

    def pick_move(self, facts: Any) -> Move:
        board, thief, left, here = self._read(facts)
        if thief is None or not self._won(board, here, thief, left):
            return super().pick_move(facts)   # the sealing plan's approach march
        pocket = self._pocket(board, thief)
        best = None
        for move in sorted(getattr(facts, "legal", ()), key=lambda m: m.value):
            dr, dc = board.delta_for(move)
            land = (here[0] + dr, here[1] + dc)
            if not board.is_open(land) or land not in pocket:
                continue
            if land == thief:
                return move
            if forced_capture(pocket, land, thief, frozenset(), left):
                key = (Board.manhattan(land, thief), move.value)
                if best is None or key < best[0]:
                    best = (key, move)
        return best[1] if best else super().pick_move(facts)
