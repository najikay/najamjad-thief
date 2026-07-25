"""Barrier planning — the cop's real weapon.

Chasing on a 7x7 board is close to hopeless on its own: the thief moves every
time we do, so raw pursuit converges slowly and 35 steps is not many. Barriers
change the shape of the problem. They are permanent, they cost only the turn
that places them, and each one permanently removes an escape route from the
thief's world.

The planner values a placement by how much it shrinks the *believed* freedom of
the thief, weighted by how likely we think the thief is to be there — and it
refuses placements that would wall us off from our own quarry, which is the
classic way to lose a won position.
"""

from dataclasses import dataclass

from ..domain.board import Board
from ..domain.params import Position
from .base import escape_routes, reachable_within

# A placement that captures outright dwarfs any positional gain.
CAPTURE_SCORE = 1_000.0
# Below this belief mass a cell is not worth a barrier; spending the quota on
# noise is how a cop reaches step 30 with nothing to show for it.
MIN_BELIEF_TO_SPEND = 0.02


@dataclass(frozen=True)
class BarrierPlan:
    """A candidate placement and why it scored as it did."""

    cell: Position
    score: float
    reason: str


def candidate_cells(board: Board, cop_cell: Position) -> list[Position]:
    """Cells the Barrier Law permits: our own, or one orthogonal step away."""
    options = [cop_cell, *[(cop_cell[0] + dr, cop_cell[1] + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]]
    return [cell for cell in options if board.is_open(cell)]


def score_placement(
    board: Board,
    cell: Position,
    belief: dict[Position, float],
    cop_cell: Position,
) -> BarrierPlan:
    """Value one placement by the freedom it removes from the likely thief."""
    mass_here = belief.get(cell, 0.0)
    if mass_here >= max(belief.values(), default=0.0) and mass_here > 0.5:
        return BarrierPlan(cell, CAPTURE_SCORE * mass_here, "likely capture-by-barrier")

    walled = board.with_barrier(cell)
    if not _still_reachable(walled, cop_cell, belief):
        return BarrierPlan(cell, -1.0, "would wall us away from the thief")

    gain = 0.0
    for neighbour, probability in belief.items():
        if probability < MIN_BELIEF_TO_SPEND:
            continue
        before = escape_routes(board, neighbour)
        after = escape_routes(walled, neighbour)
        gain += probability * (before - after)
    return BarrierPlan(cell, gain, f"removes {gain:.2f} weighted escape routes")


def _still_reachable(walled: Board, cop_cell: Position, belief: dict[Position, float]) -> bool:
    """True when meaningful belief mass remains reachable after the placement."""
    live = {cell for cell, probability in belief.items() if probability >= MIN_BELIEF_TO_SPEND}
    if not live:
        return True
    horizon = reachable_within(walled, cop_cell, walled.size * 2)
    return bool(live & horizon)


def plan_barrier(
    board: Board,
    cop_cell: Position,
    belief: dict[Position, float],
    barriers_left: int,
    threshold: float = 0.15,
) -> BarrierPlan | None:
    """Choose a placement, or None when moving is the better use of the turn.

    `threshold` is the price of a turn: placing a barrier means not chasing, so
    a placement must buy at least this much weighted freedom to be worth it.
    """
    if barriers_left <= 0:
        return None
    plans = [score_placement(board, cell, belief, cop_cell) for cell in candidate_cells(board, cop_cell)]
    if not plans:
        return None
    best = max(plans, key=lambda plan: plan.score)
    return best if best.score >= threshold else None
