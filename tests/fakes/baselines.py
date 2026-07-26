"""Baseline opponents: the obvious strategy, played competently.

These are the yardstick the league is really measured against. Most teams will
ship something close to this — chase the most likely cell, or run from it — so
"our brain beats greedy" is the claim worth being able to prove, and to notice
losing.

They are given exactly what a real brain is given, so they can be dropped into
the actual orchestrator rather than a simplified loop. A baseline that cheated
by reading the true position would flatter us into thinking we had a strategy.
"""

from dataclasses import dataclass
from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.strategy.base import move_away, move_towards


@dataclass
class _Baseline:
    """Shared plumbing: how a brain gets the board it reasons over."""

    # Same contract as the real brains. The board is supplied live because
    # barriers appear mid-game, and `TurnFacts` deliberately does not carry it —
    # a brain without a supplier raises the moment it is asked to move.
    board_supplier: Any = None

    def _board(self, facts: Any) -> Any:
        """The current board, from the supplier or from the facts."""
        if self.board_supplier is not None:
            return self.board_supplier()
        return facts.board

    @staticmethod
    def _most_likely(facts: Any) -> Any:
        """The cell the belief map favours, or None when it is empty."""
        belief = getattr(facts, "belief", None) or {}
        return max(belief, key=lambda cell: belief[cell]) if belief else None

    def pick_barrier(self, facts: Any) -> None:
        """No baseline spends a barrier — that is what makes it the baseline."""
        return None


@dataclass
class GreedyCop(_Baseline):
    """The obvious cop: walk at the most likely cell every turn, never build."""

    name: str = "greedy-cop"

    def pick_move(self, facts: Any) -> Move:
        """Step towards the belief peak."""
        target = self._most_likely(facts)
        if target is None:
            return Move.STAY
        return move_towards(self._board(facts), facts.own_position, target, facts.legal)


@dataclass
class GreedyThief(_Baseline):
    """The obvious thief: maximise distance, ignore the walls closing in."""

    name: str = "greedy-thief"

    def pick_move(self, facts: Any) -> Move:
        """Step away from the belief peak."""
        threat = self._most_likely(facts)
        if threat is None:
            return Move.STAY
        return move_away(self._board(facts), facts.own_position, threat, facts.legal)
