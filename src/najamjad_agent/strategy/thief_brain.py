"""The thief's move policy — survive 35 steps, don't merely run.

The win condition shapes everything: the thief does not need to escape, only to
last. That makes greedy distance-maximisation a trap, because the move that puts
the most cells between us and the cop is very often the one that backs us into a
corner where a single barrier ends the game.

So a move is scored on three things at once:

* **Distance** under our belief about where the cop is;
* **Room** — escape routes and reachable freedom, which is what the cop's
  barriers are actually attacking;
* **Scent** — we cannot fake our trail (book PAGE 22), but we can avoid
  re-walking ground we have already perfumed, which is the only way to keep our
  emitted evidence from pointing straight at us.

A two-ply lookahead asks what the cop can do next, so we avoid moves that look
safe now and are lost a turn later.
"""

from dataclasses import dataclass
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from . import thief_safety
from .base import apply, expected_distance
from .thief_escape import corridor_risk, escape_routes, trap_penalty

DISTANCE_WEIGHT = 1.0
ROOM_WEIGHT = 0.9
SCENT_WEIGHT = 0.6
RISK_WEIGHT = 2.5
# One ply of cop response. Deeper search buys little on a 7x7 board and costs
# time we owe the 30 s turn budget.
LOOKAHEAD = 1


@dataclass
class ThiefBrain:
    """Deterministic evasion policy for the thief role."""

    board_supplier: Any = None
    horizon: int = 3
    #: How many steps from the survival horizon the policy switches to stalling.
    #: Surviving to step 35 and surviving to step 100 score the same, so the last
    #: turns are a different game: a move that is safe *now* beats one that is
    #: better positioned for a future that will not arrive. Three, because a
    #: corridor takes two moves to escape and one to enter.
    stall_trigger: int = 3
    #: How much the endgame weights room over distance. High enough to dominate
    #: position, not so high that the thief walks toward the cop to find space.
    stall_room_weight: float = 4.0

    def steps_remaining(self, facts: Any) -> int:
        """Turns left before survival, or a large number when nobody says.

        Most callers do not supply a countdown, and a thief that assumed the
        endgame by default would spend thirty steps hugging open ground instead
        of getting away.
        """
        left = getattr(facts, "steps_remaining", None)
        return int(left) if isinstance(left, int) else self.stall_trigger + 1

    def is_endgame(self, facts: Any) -> bool:
        """Whether the horizon is close enough to stop taking chances."""
        return self.steps_remaining(facts) <= self.stall_trigger

    def pick_move(self, facts: Any) -> Move:
        """Choose the move that best preserves survival, not just distance.

        The safety rule owns this decision whenever we know where the cop is,
        which — given the pheromone field's freshest deposit is always its
        unique maximum — is every turn against an opponent who transmits one.
        The old weighted sum survives only as the fallback for a peer who sends
        nothing, and it is a fallback because it lost three games as a policy.
        """
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        belief = dict(getattr(facts, "belief", {}) or {})
        origin: Position = getattr(facts, "own_position", (0, 0))
        cop = self._cop_cell(belief)
        if cop is not None:
            # No `barriers_left` argument: `facts.barriers_left` is *our* quota,
            # and a thief's is always zero, so passing it disabled the cut-cell
            # guard for the only role that needs it. The board carries the
            # cop's true remaining count.
            return self._break_tie(thief_safety.choose(board, origin, cop, legal), facts)
        scent = dict(getattr(facts, "scent", {}) or {})
        endgame = self.is_endgame(facts)
        return max(
            legal,
            key=lambda move: (
                self._value(board, origin, move, belief, scent, endgame),
                move.value,
            ),
        )

    def _cop_cell(self, belief: dict[Position, float]) -> Position | None:
        """The cop's cell when the belief names one, else None."""
        if not belief:
            return None
        return max(belief, key=lambda cell: belief[cell])

    def _break_tie(self, tied: tuple[Move, ...], facts: Any) -> Move:
        """Pick among equally safe moves, unpredictably but never unsafely.

        Randomising *only* within the tied set is the whole discipline. A
        scripted opponent solved our previous thief by replaying one line
        against it three times, so playing the same game twice is a real cost —
        but so is trading a safe move for a varied one, and this trades none.

        Seeded from the sub-game so a match stays reproducible for the audit:
        the same game replays identically, different games do not.
        """
        if len(tied) == 1:
            return tied[0]
        seed = (int(getattr(facts, "sub_game", 1)), int(getattr(facts, "step", 0)))
        return sorted(tied, key=lambda move: move.value)[hash(seed) % len(tied)]

    def pick_barrier(self, facts: Any) -> Position | None:
        """Thieves never place barriers (cop-only power, book Ch. 3)."""
        return None

    def _value(
        self,
        board: Board,
        origin: Position,
        move: Move,
        belief: dict[Position, float],
        scent: dict[Position, float],
        endgame: bool = False,
    ) -> float:
        """Higher is better: distance and room, minus risk and self-betrayal.

        In the endgame the weights change rather than the shape: room is worth
        several times more and raw distance almost nothing, because a cell we
        cannot be trapped in for two turns wins a game that a cell three steps
        further away does not.
        """
        landing = apply(board, origin, move)
        if not board.is_open(landing):
            return float("-inf")
        distance = expected_distance(belief, landing) if belief else 0.0
        room = escape_routes(board, landing)
        risk = corridor_risk(board, landing, self.horizon) + trap_penalty(board, landing)
        leak = scent.get(landing, 0.0)
        worst_next = self._worst_case(board, landing, belief)
        if endgame:
            # Room dominates and distance nearly vanishes: with a step or two
            # left, a cell we cannot be trapped in wins the game that a cell
            # three squares further away does not. Risk keeps its full weight —
            # the point is to stop gambling, not to stop looking.
            return (
                self.stall_room_weight * room
                - RISK_WEIGHT * risk
                - SCENT_WEIGHT * leak
                + DISTANCE_WEIGHT * worst_next
            )
        return (
            DISTANCE_WEIGHT * distance
            + ROOM_WEIGHT * room
            - RISK_WEIGHT * risk
            - SCENT_WEIGHT * leak
            + DISTANCE_WEIGHT * worst_next
        )

    def _worst_case(self, board: Board, landing: Position, belief: dict[Position, float]) -> float:
        """Distance we would still hold after the cop's best reply.

        Without this, a move that maximises distance now but hands the cop a
        free cut-off looks identical to one that keeps us genuinely clear.
        """
        if not belief:
            return 0.0
        threat = max(belief, key=lambda cell: belief[cell])
        approaches = board.neighbours(threat) or (threat,)
        return min(Board.manhattan(landing, approach) for approach in approaches)

    def _board(self, facts: Any) -> Board:
        """The board to reason over, supplied by the orchestrator or the facts."""
        if self.board_supplier is not None:
            return self.board_supplier()
        return facts.board
