"""The cop that plays the solved table instead of guessing at thresholds.

`strategy/solver.py` has always computed the exact answer: by backward induction
to a fixed point it returns every `(cop, thief)` position, thief to move, from
which the cop can *force* a capture on the current board. `thief_brain` has
consulted it since it was written. `cop_brain` never has — it ranked moves by a
weighted distance heuristic and spent barriers when a hand-tuned score crossed a
hand-tuned threshold. Those thresholds were calibrated against near-delta
beliefs and score about 0.35 against a real scent-shaped one, which is how a
counted series was played with two barriers of a possible forty-two while the
thief sat at distance 2 for twenty-seven consecutive steps.

The table removes the guessing entirely, and the classical result says why it
must: a 7x7 grid is a product of two paths, its cop number is 2 (Maamoun &
Meyniel), so on an *intact* board one cop can never force a capture and the
win set contains only the co-located pairs. Barriers are the only thing that
changes that. So the whole cop problem is a search over wall placements for one
that turns an unwinnable position into a winnable one — and `solver` answers
"is this position winnable" exactly, per wall configuration, cached.

Hence the policy, which has no tunable constants at all:

  1. if the position is already a forced win, play the move that keeps it one
     and shortens the chase;
  2. otherwise spend a barrier that *makes* it a forced win — checked, not
     scored;
  3. otherwise spend a barrier that strictly shrinks the thief's world, since
     every won position is reached through smaller worlds;
  4. otherwise close the distance.

Steps 1 and 2 are exact. Steps 3 and 4 are the approach march, and they are the
only part that can be wrong.
"""

from dataclasses import dataclass
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import confident_peak
from .cop_brain import CopBrain
from .solver import cop_can_force_capture, losing_states
from .territory import component

#: Below this many open cells the thief's world is small enough that shrinking
#: it further is worth a barrier even without a proven win, because the table's
#: own boundary is width three: 2xN and 3x3 fall to a cop holding one barrier,
#: 3x4 and 3x5 to two, and 4x4 holds at every budget. Fifteen cells fall,
#: sixteen hold, so a region at or under sixteen is one or two walls from won.
WORTH_SHRINKING = 16


@dataclass
class TableCop(CopBrain):
    """The shipped cop, plus the one override that is provably never wrong.

    When `solver` says the current position is a forced win, this plays the move
    that keeps it a forced win and shortens the chase. When it says nothing of
    the kind — which on an intact 7x7 is almost always, because the cop number of
    a grid is 2 — it defers entirely to the heuristic cop underneath.

    That narrowness is the point, and it was earned. A barrier-hungry preset, a
    sealing plan, and the two joined to the table all measured *worse* than the
    shipped cop against every thief we can run. The table is the only component
    that cannot be wrong: it overrides only where it has proved a win, and a
    proved win is not a matter of taste.
    """

    def _read(self, facts: Any) -> tuple[Board, Position | None, int, Position]:
        board = self._board(facts)
        belief = dict(getattr(facts, "belief", {}) or {})
        return (board, confident_peak(belief), int(getattr(facts, "barriers_left", 0) or 0),
                getattr(facts, "own_position", (0, 0)))

    def _placements(self, board: Board, here: Position, thief: Position) -> list[Position]:
        """Cells the Barrier Law allows, that keep us and the thief together.

        Sealing the thief away from us is the classic way to throw a won
        position, so a placement that puts it in another component is refused
        however good it looks.
        """
        law = [here, *board.neighbours(here)]
        out = []
        for cell in law:
            if not board.is_open(cell) or cell in (thief, here):
                continue
            walled = board.with_barrier(cell)
            if not walled.neighbours(here) or thief not in component(walled, here):
                continue
            out.append(cell)
        return out

    def pick_barrier(self, facts: Any) -> Position | None:
        """Unchanged from the shipped cop, deliberately.

        Three attempts to be cleverer here all measured *worse* than doing
        nothing: a barrier-hungry preset caught 2 of 3 archived lines where
        pursuit caught 3, the sealing plan converted a random walker at step 27
        instead of step 5, and joining the plan to the table lost to that walker
        outright. Walls cost the turn that would have closed the distance, and
        against every opponent we have actually met, closing wins more often.
        So this class changes exactly one thing, and it is the one thing that
        cannot cost us a game.
        """
        return super().pick_barrier(facts)

    def pick_move(self, facts: Any) -> Move:
        """Hold the win if we have one; otherwise close."""
        board, thief, _left, here = self._read(facts)
        if thief is None:
            return super().pick_move(facts)
        legal = tuple(getattr(facts, "legal", ()))
        if cop_can_force_capture(board, here, thief):
            losing = losing_states(board)
            keeps = []
            for move in sorted(legal, key=lambda m: m.value):
                dr, dc = board.delta_for(move)
                land = (here[0] + dr, here[1] + dc)
                if not board.is_open(land):
                    continue
                if land == thief or (land, thief) in losing:
                    keeps.append((Board.manhattan(land, thief), move.value, move))
            if keeps:
                return min(keeps)[2]
        return super().pick_move(facts)   # the sealing plan's approach march


def plays_full(strength: str) -> bool:
    """Reduced strength keeps the old naive pursuit, exactly as before."""
    from ..shared.strength import AT_FULL_STRENGTH

    return str(strength) in AT_FULL_STRENGTH
