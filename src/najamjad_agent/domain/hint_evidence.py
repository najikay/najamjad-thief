"""Turning an opponent's words into evidence — and catching them lying.

A hint is *testimony*, not observation: the opponent may lie freely (it is their
only deception channel). So a claim is never applied at face value. It becomes a
per-cell likelihood scaled by a **credibility coefficient** earned over the
series, and it is cross-examined against the scent field, which cannot be faked.

Book PAGE 46 worked example: the thief claims "I moved north" while the northern
cells read 0.00 and a fresh 0.81 trail sits to the south-east. The claim is
refuted, credibility drops, and the belief map stays anchored on the scent mass.
"""

from dataclasses import dataclass

from ..constants import Move
from .params import Position

BOOST = 1.0
PENALTY = 0.8
MIN_LIKELIHOOD = 0.05
DEFAULT_CREDIBILITY = 0.5
LEARNING_RATE = 0.25
SCENT_NOISE_FLOOR = 0.05
# A verdict needs at least this much displacement along the claimed axis.
# Summing the whole scent cloud instead lets a trail's lateral spread "confirm"
# a perpendicular claim (an eastward trail appears to support "I went south",
# because emission bleeds into southern rows), so we test the displacement of
# the fresh mass centroid and stay silent inside the tolerance band.
DISPLACEMENT_TOLERANCE = 1.0


@dataclass(frozen=True)
class HintClaim:
    """A decoded hint: the direction and/or landmark the opponent asserts."""

    direction: Move | None = None
    landmark_cells: tuple[Position, ...] = ()
    text: str = ""

    @property
    def is_informative(self) -> bool:
        """False when nothing usable was decoded (parse failure or empty hint)."""
        return self.direction is not None or bool(self.landmark_cells)


class CredibilityTracker:
    """How much this opponent's words have been worth so far, in [0, 1].

    Single entry point (`record`) so credibility can only move through the
    audited rule; strategy code reads `coefficient` but never assigns it.
    """

    def __init__(self, coefficient: float = DEFAULT_CREDIBILITY) -> None:
        """Start neutral unless a prior from an earlier mini-game is supplied."""
        self._coefficient = min(1.0, max(0.0, coefficient))

    @property
    def coefficient(self) -> float:
        """Current credibility weight applied to this opponent's claims."""
        return self._coefficient

    def record(self, consistent: bool) -> float:
        """Fold one verdict in: confirmed claims raise trust, refuted ones cut it."""
        if consistent:
            self._coefficient += LEARNING_RATE * (1.0 - self._coefficient)
        else:
            self._coefficient -= LEARNING_RATE * self._coefficient
        self._coefficient = min(1.0, max(0.0, self._coefficient))
        return self._coefficient


def _direction_component(delta: Position, move: Move) -> int:
    """How far `delta` points along `move` (positive = same direction)."""
    row_delta, col_delta = delta
    if move is Move.NORTH:
        return -row_delta
    if move is Move.SOUTH:
        return row_delta
    if move is Move.EAST:
        return col_delta
    if move is Move.WEST:
        return -col_delta
    return 0


def claim_likelihood(
    cells: tuple[Position, ...],
    claim: HintClaim,
    reference: Position,
    credibility: float,
) -> dict[Position, float]:
    """Per-cell likelihood implied by a claim, scaled by credibility.

    With zero credibility (or an uninformative hint) every weight is 1.0 — an
    identity update, so a hint we cannot trust or parse changes nothing.
    """
    if not claim.is_informative or credibility <= 0.0:
        return dict.fromkeys(cells, 1.0)
    landmarks = set(claim.landmark_cells)
    likelihood: dict[Position, float] = {}
    for cell in cells:
        delta = (cell[0] - reference[0], cell[1] - reference[1])
        supports = cell in landmarks
        if claim.direction is not None and _direction_component(delta, claim.direction) > 0:
            supports = True
        weight = 1.0 + credibility * BOOST if supports else 1.0 - credibility * PENALTY
        likelihood[cell] = max(MIN_LIKELIHOOD, weight)
    return likelihood


def scent_consistency(
    claim: HintClaim,
    intensities: dict[Position, float],
    reference: Position,
) -> str:
    """Cross-examine a claim against the scent field.

    Returns "consistent", "refuted", or "unknown" — the verdict that feeds
    `CredibilityTracker.record` and, in turn, every later hint's weight.
    """
    if claim.direction is None or not intensities:
        return "unknown"
    fresh = {cell: value for cell, value in intensities.items() if value > SCENT_NOISE_FLOOR}
    mass = sum(fresh.values())
    if mass <= 0.0:
        return "unknown"
    centroid_row = sum(cell[0] * value for cell, value in fresh.items()) / mass
    centroid_col = sum(cell[1] * value for cell, value in fresh.items()) / mass
    delta = (centroid_row - reference[0], centroid_col - reference[1])
    component = _direction_component(delta, claim.direction)  # type: ignore[arg-type]
    if component > DISPLACEMENT_TOLERANCE:
        return "consistent"
    if component < -DISPLACEMENT_TOLERANCE:
        return "refuted"
    return "unknown"
