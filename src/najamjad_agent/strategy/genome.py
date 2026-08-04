"""A thief strategy as a set of numbers, so strategies can be bred rather than argued about.

Every dial `ThiefBrain` exposes, plus the weights inside its fallback objective,
collected into one value object that can be mutated, compared and replayed.

**Why this and not a swarm of LLM agents.** The obvious version of "evolve a
strategy" is to spawn agents, have them play, and keep the winner. A duel here
is *milliseconds*: this runs thousands of games in the time a handful of agents
would take to play a dozen, every result replays exactly from its seed, and the
whole search costs nothing per generation. Reproducibility is not a nicety —
rule 49 means a grader can re-run it, and a tuning result nobody can reproduce
is an opinion with a number attached.

**What it may not do.** A genome cannot switch the safety invariant off. The
distance-2 rule and the exact solve are theorems, not preferences: one cop
provably cannot catch a careful thief, so a search allowed to discard them would
spend its budget rediscovering that being caught is bad. Evolution tunes the
heuristics that pick *among* provably safe moves, and nothing else.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from typing import Any

#: Each tunable and the range a mutation may explore, as (low, high).
#: Ranges are deliberately narrow around the shipped values: this is a local
#: search for a better setting, not a hunt for a different game.
BOUNDS: dict[str, tuple[float, float]] = {
    "horizon": (1.0, 5.0),
    "stall_trigger": (1.0, 6.0),
    "stall_room_weight": (1.0, 8.0),
    "distance_weight": (0.0, 3.0),
    "room_weight": (0.0, 3.0),
    "scent_weight": (0.0, 2.0),
    "risk_weight": (0.0, 5.0),
    "confident_share": (2.0, 8.0),
}
#: Dials that must stay whole numbers — they count turns, not weights.
INTEGRAL = frozenset({"horizon", "stall_trigger"})


@dataclass(frozen=True)
class Genome:
    """One candidate thief strategy."""

    horizon: float = 3.0
    stall_trigger: float = 3.0
    stall_room_weight: float = 4.0
    distance_weight: float = 1.0
    room_weight: float = 0.9
    scent_weight: float = 0.6
    risk_weight: float = 2.5
    confident_share: float = 4.0

    @property
    def name(self) -> str:
        """A short stable id, so a result table can be read and re-run."""
        digest = hashlib.blake2b(repr(asdict(self)).encode(), digest_size=4)
        return digest.hexdigest()

    def as_brain_kwargs(self) -> dict[str, Any]:
        """The subset `ThiefBrain` accepts as constructor arguments."""
        return {
            "horizon": int(self.horizon),
            "stall_trigger": int(self.stall_trigger),
            "stall_room_weight": float(self.stall_room_weight),
        }

    def clamped(self) -> Genome:
        """This genome with every dial inside its bounds and integers whole."""
        fixed: dict[str, float] = {}
        for field, (low, high) in BOUNDS.items():
            value = min(high, max(low, float(getattr(self, field))))
            fixed[field] = round(value) if field in INTEGRAL else round(value, 3)
        return replace(self, **fixed)


def mutate(genome: Genome, rng: Any, strength: float = 0.25) -> Genome:
    """Nudge a genome that is doing well but was beaten.

    Input: the genome, a seeded `random.Random`, and how hard to push.
    Output: a new clamped genome.
    Setup: none — the rng carries all the state, so a run replays from its seed.

    A *local* move on one or two dials rather than a fresh draw. A loss is
    evidence that this genome is imperfect, not evidence that everything about
    it is wrong, and re-rolling the whole thing on every loss is random search
    wearing evolution's clothes.
    """
    fields = list(BOUNDS)
    changed = rng.sample(fields, k=min(2, len(fields)))
    values: dict[str, float] = {}
    for field in changed:
        low, high = BOUNDS[field]
        span = (high - low) * strength
        values[field] = float(getattr(genome, field)) + rng.uniform(-span, span)
    return replace(genome, **values).clamped()


def random_genome(rng: Any) -> Genome:
    """A fresh draw, for a lineage that has lost repeatedly.

    Repeated losses say the neighbourhood is bad, not the step size. Mutation
    would keep searching the same basin; this leaves it.
    """
    return Genome(**{field: rng.uniform(low, high) for field, (low, high) in BOUNDS.items()}).clamped()


def shipped() -> Genome:
    """The values the agent currently ships, as the baseline to beat.

    The search has to justify replacing a measured configuration, so the
    incumbent competes on the same terms as every challenger.
    """
    return Genome()
