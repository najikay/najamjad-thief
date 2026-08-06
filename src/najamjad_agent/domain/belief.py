"""Bayesian belief over the opponent's position — the core of our tactics.

The game is a Dec-POMDP: we never observe the opponent, only a decaying scent
field and a hint that may be a lie. This module maintains P(opponent at cell)
and fuses three evidence sources, in a fixed order that matters:

1. `diffuse` — the motion model: the opponent moved one orthogonal step or
   stayed, so mass spreads through *open* cells only (barriers are declared
   publicly, so we know the walls they cannot cross).
2. `update_scent` — physical evidence. Scent cannot be faked, so it is applied
   as a hard likelihood.
3. `update_hint` (via `hint_evidence`) — testimony, applied last and weighted by
   how credible that opponent has proven to be.

Ordering rule (FR-STR-1): testimony is fused *after* physics and can only
re-weight mass that physics still allows, so a confident lie can never move
belief onto a cell the scent has ruled out.
"""

from .board import Board
from .params import Position

# Floor kept on every open cell so a single mistaken observation can never make
# a cell permanently impossible (a zero can never recover under multiplication).
MIN_CELL_PROBABILITY = 1e-6
# Weight given to the *current* scent observation on top of the Bayes step.
# Pure multiplicative accumulation double-counts the trail (the scent field is
# already cumulative), so a cell that led early keeps an unearned advantage and
# the peak lags several cells behind a moving opponent — proven by the
# convergence scenarios. Mixing in the fresh observation makes the filter
# robust to that model mismatch and lets belief re-lock within one turn.
OBSERVATION_WEIGHT = 0.5
# Likelihood floor: an unscented cell is unlikely, not impossible.
LIKELIHOOD_FLOOR = 0.01
# Contrast exponent on the scent likelihood. At 10% decay per turn the head of a
# trail is only ~11% stronger than the cell behind it, so raw intensity is a
# nearly-flat signal and diffusion parks belief mid-trail. The opponent is at the
# *freshest* scent, not merely strong scent, so we sharpen the likelihood (a
# lower observation temperature) to make the head dominate its own tail.
SCENT_SHARPNESS = 8.0


class BeliefGrid:
    """A normalised probability distribution over the opponent's position."""

    def __init__(self, board: Board, known_empty: tuple[Position, ...] = ()) -> None:
        """Start from a uniform prior over every open cell."""
        self._board = board
        candidates = [cell for cell in board.cells() if board.is_open(cell)]
        self._values = {cell: 1.0 for cell in candidates if cell not in known_empty}
        self.normalise()

    @property
    def board(self) -> Board:
        """Board the belief is defined over."""
        return self._board

    def probability_at(self, cell: Position) -> float:
        """Current belief that the opponent occupies `cell`."""
        return self._values.get(cell, 0.0)

    def total(self) -> float:
        """Sum of all probabilities (1.0 for a healthy distribution)."""
        return sum(self._values.values())

    def peak(self) -> Position | None:
        """Most likely opponent cell, ties broken deterministically."""
        if not self._values:
            return None
        best = max(self._values.values())
        return min(cell for cell, value in self._values.items() if value == best)

    def as_dict(self) -> dict[Position, float]:
        """Snapshot for the UI heatmap and logs."""
        return dict(self._values)

    def normalise(self) -> None:
        """Rescale to a valid distribution, recovering from total collapse."""
        total = sum(self._values.values())
        if total <= 0.0:
            # Every hypothesis was eliminated (contradictory evidence): fall back
            # to uniform over open cells rather than carry a broken distribution.
            self._values = {cell: 1.0 for cell in self._board.cells() if self._board.is_open(cell)}
            total = float(len(self._values)) or 1.0
        self._values = {cell: value / total for cell, value in self._values.items()}

    def diffuse(self, stay_weight: float = 0.2) -> None:
        """Spread mass to open neighbours: the opponent took one step or stayed."""
        spread: dict[Position, float] = {}
        for cell, value in self._values.items():
            neighbours = self._board.neighbours(cell)
            spread[cell] = spread.get(cell, 0.0) + value * stay_weight
            if not neighbours:
                spread[cell] = spread.get(cell, 0.0) + value * (1.0 - stay_weight)
                continue
            share = value * (1.0 - stay_weight) / len(neighbours)
            for neighbour in neighbours:
                spread[neighbour] = spread.get(neighbour, 0.0) + share
        self._values = {cell: value for cell, value in spread.items() if self._board.is_open(cell)}
        self.normalise()

    def update_scent(self, intensities: dict[Position, float], trust: float = 1.0) -> None:
        """Fuse the observed scent field as a likelihood over cells.

        Applies a Bayes step and then mixes in the raw observation (see
        `OBSERVATION_WEIGHT`) so the freshest evidence always outranks a stale
        prior — without that, belief trails a moving opponent by several cells.
        """
        strongest = max(intensities.values(), default=0.0)
        if strongest <= 0.0:
            return  # No evidence this turn: leave the distribution untouched.
        # Additive floor, not a clamp: keeps every likelihood strictly ordered by
        # observed intensity (a clamp would make "faint scent" and "no scent"
        # indistinguishable after sharpening) while staying above zero.
        likelihood = {
            cell: LIKELIHOOD_FLOOR
            + (1.0 - LIKELIHOOD_FLOOR)
            * ((1.0 - trust) + trust * (intensities.get(cell, 0.0) / strongest)) ** SCENT_SHARPNESS
            for cell in self._values
        }
        posterior = {cell: self._values[cell] * weight for cell, weight in likelihood.items()}
        posterior_mass = sum(posterior.values())
        likelihood_mass = sum(likelihood.values())
        if posterior_mass <= 0.0:
            posterior, posterior_mass = likelihood, likelihood_mass
        self._values = {
            cell: max(
                MIN_CELL_PROBABILITY,
                (1.0 - OBSERVATION_WEIGHT) * posterior[cell] / posterior_mass
                + OBSERVATION_WEIGHT * likelihood[cell] / likelihood_mass,
            )
            for cell in self._values
        }
        self.normalise()

    def apply_likelihood(self, likelihood: dict[Position, float]) -> None:
        """Fuse an arbitrary per-cell likelihood (used for hint testimony)."""
        for cell in self._values:
            weight = likelihood.get(cell, 1.0)
            self._values[cell] = max(self._values[cell] * max(0.0, weight), MIN_CELL_PROBABILITY)
        self.normalise()

    def observe_reach(self, cells: tuple[Position, ...], confidence: float = 1.0) -> None:
        """Fuse a public declaration that narrows the opponent to `cells`.

        The fourth evidence source, and the only one that works against an
        opponent who transmits nothing. A capture claim names the cop's exact
        cell and a barrier names a five-cell reach set (see
        `domain/cop_sighting.py`); both are mandatory and both are truthful under
        rules 15-16 and 21-22. Against uoh-sqak, who send no scent and no hints,
        these were the *only* position disclosures in the whole series — 289 of
        them — and the belief ignored every one.

        `confidence` is the posterior mass the declaration is worth — the share
        of belief that ends up *inside* `cells` — and the rest is left spread
        over the board in its existing proportions. That is Jeffrey conditioning,
        and stating it as a mass rather than as a per-cell multiplier is not
        cosmetic: a multiplier interacts with how many cells happen to be on each
        side, and at 49 cells a barrier's 4-cell reach set finished with *less*
        mass than the 44 cells it had just ruled out. The name has to mean what
        it says or the dial cannot be tuned by anyone, including us.

        Nothing reaches a hard zero. `MIN_CELL_PROBABILITY` survives the update
        so a mistaken observation stays recoverable — a cell driven to zero can
        never come back under multiplication, and this is the one evidence
        source with no physics behind it to correct a lie.

        A declaration naming nothing we track is *ignored*, not applied. Zeroing
        the whole grid would trip `normalise`'s collapse recovery and reset us to
        uniform — strictly worse than the belief we already held, and reachable
        by an opponent simply by declaring a cell we think is walled.
        """
        wanted = set(cells) & set(self._values)
        if not wanted:
            return
        share = max(0.0, min(1.0, confidence))
        inside = sum(self._values[cell] for cell in wanted)
        outside = sum(value for cell, value in self._values.items() if cell not in wanted)
        if inside <= 0.0 or outside <= 0.0:
            # One side holds everything already; rescaling it against an empty
            # other side would divide by zero for no gain.
            return
        self._values = {
            cell: max(
                MIN_CELL_PROBABILITY,
                share * value / inside
                if cell in wanted
                else (1.0 - share) * value / outside,
            )
            for cell, value in self._values.items()
        }
        self.normalise()

    def exclude(self, cells: tuple[Position, ...]) -> None:
        """Zero out cells the opponent provably does not occupy (e.g. our own)."""
        for cell in cells:
            if cell in self._values:
                self._values[cell] = 0.0
        self.normalise()
