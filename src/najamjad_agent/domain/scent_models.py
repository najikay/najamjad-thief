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


def fresh_deposit(now: dict[str, float], previous: dict[str, float],
                  model: ScentModel, decay: float) -> dict[Cell, float]:
    """What the emitter laid down THIS turn, recovered from two frames.

    A transmitted field is cumulative: it holds where they are *and* everywhere
    they have been. Under `multiplicative_book_v1` that is not a minor nuisance —
    `clamp((1 - rho) * tau + delta, 0, 0.9)` drives the whole recent trail to the
    ceiling, so a six-step walk shares its 0.90 peak across six cells and the
    emitter's own square is not recoverable from the field at all. Measured
    2026-08-21, and it is a property of the model rather than a fault in it.

    But the frames are two observations of one process, and the update is
    invertible. Age the previous frame by the model's own decay and subtract:
    what remains is the kernel the emitter deposited this turn, centred on the
    cell it now occupies. Saturated cells contribute nothing (they clamp), and
    the outer kernel ring never clamps, so the centre stays locatable exactly
    where the raw field has given up.

    Input: the grid that just arrived and the one before it, both as sent, plus
        the agreed model and decay.
    Output: per-cell freshly-deposited intensity, positive cells only.
    Setup: needs the previous frame; the first turn of a mini-game has none and
        the caller falls back to the cumulative field.
    """
    aged: dict[Cell, float] = {}
    for key, value in (previous or {}).items():
        cell = _cell_of(key)
        if cell is None:
            continue
        aged[cell] = (1.0 - decay) * value if model is ScentModel.BOOK else max(0.0, value - decay)
    fresh: dict[Cell, float] = {}
    for key, value in (now or {}).items():
        cell = _cell_of(key)
        if cell is None:
            continue
        gain = value - aged.get(cell, 0.0)
        if gain > 0.0:
            fresh[cell] = gain
    return fresh


def _cell_of(key: str) -> Cell | None:
    """Parse a `"r,c"` wire key, returning None when malformed."""
    try:
        row, col = str(key).split(",")
        return int(row), int(col)
    except (TypeError, ValueError):
        return None


#: How strongly a matched centre outranks a poor one. The filter output is a
#: fit score in [0, sum(kernel)]; this turns it into a likelihood ratio without
#: ever reaching zero, because a cell the scent merely fails to support is
#: unlikely rather than impossible.
CENTRE_CONTRAST = 6.0


def centre_likelihood(fresh: dict[Cell, float], model: ScentModel, board_size: int,
                      grid_size: int, centre_intensity: float) -> dict[Cell, float]:
    """Per-cell likelihood that the emitter is standing there, from one deposit.

    A matched filter, and it exists because the raw field cannot answer this
    under `multiplicative_book_v1`. There the update clamps at
    `center_intensity`, so the cell the agent occupies saturates — and so does
    everywhere it has recently been. A six-step walk shares its 0.90 peak across
    six cells, and worse, the *freshest* signal is not at the centre at all: the
    centre is already clamped, so it gains nothing this turn while the newly
    reached edge gains the most. Taking the argmax of either the field or its
    increment lands one cell ahead of the truth.

    Scoring the whole kernel shape fixes both. For each candidate centre we ask
    how much of that centre's kernel the observed increment actually supports,
    `min(observed, expected)` summed over the footprint — so a clamped centre
    contributing nothing costs the candidate nothing, while the unclamped outer
    ring, which is where the information survives, decides it. Measured
    2026-08-21 on two walks under both models: the peak lands on the true cell
    and nowhere else under the book model, where the raw field was six-way
    ambiguous.

    Under `subtractive_chebyshev_v1` the raw field is already unique on the true
    cell, so this is corroboration rather than rescue — and the caller keeps the
    ordinary scent update underneath it either way.
    """
    scores: dict[Cell, float] = {}
    best = 0.0
    for row in range(board_size):
        for col in range(board_size):
            kernel = emission_field((row, col), centre_intensity, grid_size, model, board_size)
            fit = sum(min(fresh.get(cell, 0.0), weight) for cell, weight in kernel.items())
            scores[(row, col)] = fit
            best = max(best, fit)
    if best <= 0.0:
        return {}
    return {cell: (fit / best) ** CENTRE_CONTRAST for cell, fit in scores.items()}
