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

from dataclasses import dataclass, field
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import apply, escape_routes, expected_distance
from .cop_barriers import plan_barrier, stalled_bar


def _chebyshev(a: Position, b: Position) -> int:
    """King-move distance, the metric this board's movement actually uses."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

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
    # 14 barriers, **while the chase is still young**. See `stalled_threshold`
    # for the bar once it demonstrably is not.
    #
    # The value is unchanged, but the sweep behind it was void and the reasoning
    # was wrong. It ran on *replayed* opponent lines, and a replayed line is a
    # list of cells the thief is teleported through: it cannot be blocked, so
    # our barriers constrained only us — 36 of 56 archived lines put the thief
    # on a cell we had walled. Re-measured against thieves that see the live
    # board, 0.40 is right for one reason only, and it is not "walling is
    # self-harm": a thief that blunders is caught by pursuit at step 8, long
    # before a wall could pay, and every wall laid before then narrows our own
    # approach. Against 400 games of a randomly-moving thief — the faithful
    # model of this league, moaamoha's own records carry `random_move: true` —
    # 0.40 captures 396 and a flat 0.22 captures 294.
    barrier_threshold: float = 0.40
    # The bar once the chase has stalled at close range, and the reason this is
    # a phase rather than a constant.
    #
    # A thief that is still uncaught after `stall_patience` consecutive turns
    # inside `stall_close` is not blundering, it is evading, and pursuit alone
    # will not finish it: on an open 7x7 a lone cop cannot force a capture
    # (ADR-021), so the space has to shrink and barriers are the only thing that
    # shrinks it. This is the vibecode signature exactly — distance 6,6,4,4,4,2
    # and then 2 held for 28 steps, reaching 1 zero times, in all three cop
    # games of a counted series we lost 30-90 with three barriers of fourteen
    # placed. Conway's angel problem says which way to go: a blocker adding one
    # square a turn beats a king-stepping evader on a bounded board by
    # progressive encirclement, and our thief is weaker than that angel.
    #
    # Measured over 520 games per configuration — 400 against a random mover,
    # 40 each against a greedy evader, a room evader that keeps its distance and
    # its room, and our own thief:
    #
    #     cop                     random   room evader   greedy
    #     flat 0.40                396/400        9/40    40/40
    #     flat 0.22                294/400       28/40    40/40
    #     stall 8 -> 0.24          396/400       21/40    40/40
    #
    # Identical to the standing bar on the thieves we actually meet — not one
    # capture given up — and more than double the conversion against one that
    # evades properly. Neither dial is a cliff: patience 6/8/10 and a late bar
    # of 0.21/0.22/0.24 all hold 21 of 40, and only 0.24 leaves the random
    # column untouched, which is why it is the one shipped.
    stalled_threshold: float = 0.24
    #: How near the belief peak counts as "on it" for the stall test.
    stall_close: int = 3
    #: Consecutive close turns before the chase is called stalled.
    stall_patience: int = 8
    #: Turns spent close without converting. Per mini-game: `brain_factory`
    #: builds a fresh brain for each one, so this cannot leak across games.
    _stalled: int = field(default=0, init=False, repr=False)
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
        self, board: Board, origin: Position, legal: tuple, belief: dict,
        bar: float | None = None,
    ) -> Move | None:
        """The move that lands on the likeliest thief cell, if it is likely enough."""
        best, mass = None, self.claim_threshold if bar is None else bar
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
        origin: Position = getattr(facts, "own_position", (0, 0))
        # **Before the early returns, not after.** The streak counts turns spent
        # close to the thief, and a turn where a capture step was available is
        # the closest kind there is — skipping those made the count read the
        # stall as shorter than it was and cost 2 conversions in 40 against the
        # room evader (19 rather than the 21 the design was measured at).
        bar, self._stalled = stalled_bar(
            origin, belief, self._stalled, self.stall_close, self.stall_patience,
            self.barrier_threshold, self.stalled_threshold,
        )
        if self.capture_step_available(facts):
            return None
        plan = plan_barrier(
            board,
            origin,
            belief,
            int(getattr(facts, "barriers_left", 0) or 0),
            bar,
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
