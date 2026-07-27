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
    # How much belief mass must sit on the target cells before we spend one of
    # 14 barriers. Swept over three unseen seeds: 0.05 captured 4 % of games,
    # 0.15 (the value we shipped for weeks) 43-75 %, and 0.40 captured 100 % on
    # every seed tried.
    #
    # The reason is that a barrier is impassable for *both* sides. A cop that
    # walls on weak evidence fences itself away from the thief it is chasing —
    # spending barriers cheaply is not aggression, it is self-harm.
    barrier_threshold: float = 0.40
    # A field rather than a module constant so the sweep runner can actually
    # vary it. Sweeping a constant would have reported a flat line and been
    # read as "this dial does not matter".
    lookahead: int = LOOKAHEAD_STEPS
    # How much belief must sit on a cell before we step onto it and claim.
    #
    # Much lower than `barrier_threshold`, and deliberately so: the two actions
    # have opposite risk profiles. A barrier is permanent and impassable for
    # both sides, so a wrong one fences us away from the thief for the rest of
    # the game. A step is reversible — the cost of a wrong claim is that it
    # discloses our cell, which is a real price but a one-turn one.
    #
    # The value matters more than it looks. Against an opponent that concedes
    # barrier traps, enclosure wins and this dial is nearly idle. Against one
    # that does not — the course reference, and so most of the class — a claimed
    # capture is the *only* capture available, and every game of a six-game
    # rehearsal ended in survival before this existed.
    claim_threshold: float = 0.12

    def pick_move(self, facts: Any) -> Move:
        """Choose the move that best closes on the believed thief.

        A capture step comes first. Landing on the believed cell lets us claim,
        and a claim is the one capture every implementation honours — the thief
        answers from its own true position and the game ends on its word rather
        than on our guess.
        """
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        belief = dict(getattr(facts, "belief", {}) or {})
        if not belief:
            return legal[0]
        origin: Position = getattr(facts, "own_position", (0, 0))
        strike = self._capture_move(board, origin, legal, belief)
        if strike is not None:
            return strike
        spread = _diffuse(board, belief, self.lookahead)
        return min(legal, key=lambda move: (self._cost(board, origin, move, spread), move.value))

    def _capture_move(
        self, board: Board, origin: Position, legal: tuple, belief: dict
    ) -> Move | None:
        """The move that lands on the likeliest thief cell, if it is likely enough."""
        best, mass = None, self.claim_threshold
        for move in sorted(legal, key=lambda option: option.value):
            landing = apply(board, origin, move)
            weight = belief.get(landing, 0.0)
            if weight > mass:
                best, mass = move, weight
        return best

    def capture_step_available(self, facts: Any) -> bool:
        """Whether a claimable capture is one move away this turn."""
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        belief = dict(getattr(facts, "belief", {}) or {})
        if not legal or not belief:
            return False
        origin: Position = getattr(facts, "own_position", (0, 0))
        return self._capture_move(board, origin, legal, belief) is not None

    def pick_barrier(self, facts: Any) -> Position | None:
        """Place a barrier when it buys more than a step of pursuit would.

        Never when a capture is one step away. Placing a barrier costs us the
        move — the orchestrator does one or the other — so walling while
        standing next to the thief trades a capture for a wall, and against an
        opponent who does not concede enclosure it trades it for nothing.
        """
        board: Board = self._board(facts)
        belief = dict(getattr(facts, "belief", {}) or {})
        if not belief:
            return None
        if self.capture_step_available(facts):
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
