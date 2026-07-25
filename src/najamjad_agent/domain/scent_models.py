"""Pheromone emission and decay math, as a *negotiated* model.

The project book and the lecturer's reference simulator disagree here:

| aspect  | book (PAGE 43-44, binding)          | reference simulator            |
|---------|-------------------------------------|--------------------------------|
| falloff | radial, 0.90/0.62/0.42/0.20/0.14/0.04 | Chebyshev, linear (0.9/0.6/0.3) |
| decay   | relative: tau <- (1-rho)*tau        | absolute: tau <- tau - rho     |

The book governs (Appendix F is binding), so `BOOK` is our default. But rule 23
requires the emission+decay model to be exchanged with a numeric example and
SHA-256 locked with each opponent, and most teams start from the simulator — so
the model is selectable per match. Matching an opponent is then a config term,
not a code change.
"""

import hashlib
import math
from enum import Enum

from ..protocol.canonical import canonical_json

Cell = tuple[int, int]

# The book's binding worked example (PAGE 44) for a 5x5 field at centre 0.9.
BOOK_FIELD_5X5 = [
    [0.04, 0.14, 0.20, 0.14, 0.04],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.20, 0.62, 0.90, 0.62, 0.20],
    [0.14, 0.42, 0.62, 0.42, 0.14],
    [0.04, 0.14, 0.20, 0.14, 0.04],
]
# Gaussian coefficient calibrated so that rounding to 2dp reproduces
# BOOK_FIELD_5X5 exactly (locked by test_book_numeric_example_matches_exactly)
# while still generalising if a larger field is ever negotiated.
BOOK_GAUSSIAN_K = 0.378
INTENSITY_DECIMALS = 2
# Relative decay rounded to 3dp has a fixed point at 0.005 (0.005*0.9 rounds
# back to 0.005), which would keep dead trails alive forever and pollute the
# belief map. Anything below this floor is treated as gone — an order of
# magnitude under the book's faintest published value (0.04), so no tactical
# information is lost.
SCENT_EPSILON = 0.005


class ScentModel(str, Enum):
    """Which pheromone model this match runs under (a negotiated term)."""

    BOOK = "book"
    REFERENCE = "reference"


def _book_weight(row_offset: int, col_offset: int) -> float:
    """Radial weight relative to the centre intensity."""
    return math.exp(-BOOK_GAUSSIAN_K * (row_offset**2 + col_offset**2))


def _reference_weight(row_offset: int, col_offset: int, half: int) -> float:
    """Linear falloff in Chebyshev distance, as the simulator implements it."""
    steps = max(abs(row_offset), abs(col_offset))
    return max(0.0, 1.0 - steps / (half + 1))


def emission_field(
    centre: Cell,
    intensity: float,
    grid_size: int,
    model: ScentModel,
    board_size: int,
) -> dict[Cell, float]:
    """Build the emission field around `centre`, clipped to the board."""
    half = grid_size // 2
    field: dict[Cell, float] = {}
    for row_offset in range(-half, half + 1):
        for col_offset in range(-half, half + 1):
            cell = (centre[0] + row_offset, centre[1] + col_offset)
            if not (0 <= cell[0] < board_size and 0 <= cell[1] < board_size):
                continue
            if model is ScentModel.BOOK:
                weight = _book_weight(row_offset, col_offset)
            else:
                weight = _reference_weight(row_offset, col_offset, half)
            value = round(intensity * weight, INTENSITY_DECIMALS)
            if value > 0.0:
                field[cell] = value
    return field


def decay_value(value: float, decay: float, model: ScentModel) -> float:
    """Apply one full-turn decay step to a single intensity."""
    decayed = (1.0 - decay) * value if model is ScentModel.BOOK else value - decay
    # Deliberately unrounded: rounding mid-computation can nudge a value *up*
    # (0.0189 -> 0.019) and previously created a self-sustaining fixed point.
    # Intensities are rounded once, at the wire/log boundary (`snapshot`).
    if decayed < SCENT_EPSILON:
        return 0.0
    return decayed


def model_fingerprint(model: ScentModel, center: float, decay: float, grid_size: int) -> str:
    """SHA-256 over the model definition plus its numeric example.

    This is the value exchanged and locked with the opponent before a series
    (book rule 23): identical fingerprints prove both sides compute identical
    scent, so a belief disagreement can never be blamed on the physics.
    """
    example = emission_field(
        (grid_size // 2, grid_size // 2), center, grid_size, model, board_size=grid_size
    )
    payload = {
        "model": model.value,
        "center_intensity": center,
        "decay": decay,
        "grid_size": grid_size,
        "decay_mode": "relative" if model is ScentModel.BOOK else "absolute",
        "example": {f"{row},{col}": value for (row, col), value in sorted(example.items())},
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
