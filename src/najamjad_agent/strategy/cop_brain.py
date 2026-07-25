"""The cop's move policy — pursuit that accounts for what the thief will do next.

Naive pursuit (walk toward the belief peak) loses to any thief that simply runs,
because both sides move at the same speed on a small board. Two ideas fix that:

* **Interception, not chasing.** We score a move by the belief-weighted distance
  it leaves us *after the thief also moves*, so we cut corners rather than
  trailing.
* **Squeezing, not catching.** Reducing the thief's escape routes is progress
  even when distance is unchanged; combined with barriers it is how a capture
  actually happens inside 35 steps.

The brain never sees the thief's true cell — only belief. It returns a move; the
orchestrator filters legality, so a bug here is a weak move, not a forfeit.
"""

from dataclasses import dataclass
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import apply, escape_routes, expected_distance
from .cop_barriers import plan_barrier

# Weights for the move score. Distance dominates; freedom-denial breaks ties and
# steers us toward corners, which is where captures happen.
DISTANCE_WEIGHT = 1.0
FREEDOM_WEIGHT = 0.35
# How far the thief is assumed to spread before we arrive.
LOOKAHEAD_STEPS = 1


@dataclass
class CopBrain:
    """Deterministic pursuit policy for the police role."""

    board_supplier: Any = None
    barrier_threshold: float = 0.15

    def pick_move(self, facts: Any) -> Move:
        """Choose the move that best closes on the believed thief."""
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        belief = dict(getattr(facts, "belief", {}) or {})
        if not belief:
            return legal[0]
        spread = _diffuse(board, belief, LOOKAHEAD_STEPS)
        origin: Position = getattr(facts, "own_position", (0, 0))
        return min(legal, key=lambda move: (self._cost(board, origin, move, spread), move.value))

    def pick_barrier(self, facts: Any) -> Position | None:
        """Place a barrier when it buys more than a step of pursuit would."""
        board: Board = self._board(facts)
        belief = dict(getattr(facts, "belief", {}) or {})
        if not belief:
            return None
        plan = plan_barrier(
            board,
            getattr(facts, "own_position", (0, 0)),
            belief,
            int(getattr(facts, "barriers_left", 0) or 0),
            self.barrier_threshold,
        )
        return plan.cell if plan else None

    def _cost(self, board: Board, origin: Position, move: Move, belief: dict[Position, float]) -> float:
        """Lower is better: expected distance, minus the freedom we deny."""
        landing = apply(board, origin, move)
        distance = expected_distance(belief, landing)
        denial = _freedom_denied(board, landing, belief)
        return DISTANCE_WEIGHT * distance - FREEDOM_WEIGHT * denial

    def _board(self, facts: Any) -> Board:
        """The board to reason over, supplied by the orchestrator or the facts."""
        if self.board_supplier is not None:
            return self.board_supplier()
        return facts.board


def _freedom_denied(board: Board, cop_cell: Position, belief: dict[Position, float]) -> float:
    """How cornered the likely thief cells are, from where we would stand.

    Standing next to a cell we cannot enter is worthless; standing next to a
    cornered one is nearly a capture. This is what pulls the cop toward edges
    and dead ends rather than orbiting the middle of the board.
    """
    denial = 0.0
    for cell, probability in belief.items():
        if probability <= 0.0:
            continue
        routes = escape_routes(board, cell)
        adjacency = 1.0 if Board.manhattan(cop_cell, cell) <= 1 else 0.0
        denial += probability * adjacency * (4 - routes)
    return denial


def _diffuse(board: Board, belief: dict[Position, float], steps: int) -> dict[Position, float]:
    """Spread belief by the thief's own movement before we arrive.

    Intercepting where they will be beats arriving where they were — this single
    step is the difference between cutting a corner and trailing behind.
    """
    current = dict(belief)
    for _ in range(max(0, steps)):
        spread: dict[Position, float] = {}
        for cell, probability in current.items():
            neighbours = board.neighbours(cell)
            spread[cell] = spread.get(cell, 0.0) + probability * 0.2
            if not neighbours:
                spread[cell] = spread.get(cell, 0.0) + probability * 0.8
                continue
            share = probability * 0.8 / len(neighbours)
            for neighbour in neighbours:
                spread[neighbour] = spread.get(neighbour, 0.0) + share
        current = spread
    return current
