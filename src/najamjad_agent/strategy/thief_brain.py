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

    def pick_move(self, facts: Any) -> Move:
        """Choose the move that best preserves survival, not just distance."""
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        belief = dict(getattr(facts, "belief", {}) or {})
        scent = dict(getattr(facts, "scent", {}) or {})
        origin: Position = getattr(facts, "own_position", (0, 0))
        return max(
            legal,
            key=lambda move: (self._value(board, origin, move, belief, scent), move.value),
        )

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
    ) -> float:
        """Higher is better: distance and room, minus risk and self-betrayal."""
        landing = apply(board, origin, move)
        if not board.is_open(landing):
            return float("-inf")
        distance = expected_distance(belief, landing) if belief else 0.0
        room = escape_routes(board, landing)
        risk = corridor_risk(board, landing, self.horizon) + trap_penalty(board, landing)
        leak = scent.get(landing, 0.0)
        worst_next = self._worst_case(board, landing, belief)
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
