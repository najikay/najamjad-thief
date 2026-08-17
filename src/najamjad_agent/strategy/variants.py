"""Six candidates, and the warm-up that picks between them.

A warm-up is uncounted, so its six mini-games are six free experiments against
the one opponent we cannot simulate: this one. Each window plays a different
candidate — three for the cop, three for the thief, since the roles alternate and
each gets three of the six — and the counted series then plays whichever
candidate scored best *against them*, at full strength.

**Why measure at all rather than reason it out.** Offline, on 2026-08-17, all
three cop candidates failed identically against our own hardened thief and all
three caught a random walker; the ranking was flat. Yet naive pursuit caught
MOAAMOHA's thief in ten steps while our tuned pursuit held it at distance two for
twenty-seven and finished empty-handed. Our own thief is stronger than the
opponents we actually face, so a bench that ranks candidates against it ranks
them against the wrong distribution. The opponent is the instrument.

**Handicapped, not crippled.** A probe runs every candidate with its search depth
cut to a single step. That weakens all three equally without touching the dials
that give each its character, so a wall-hungry cop still prefers walls and a
room-hungry thief still prefers room — the ranking reflects strategy rather than
depth, and a team reading our warm-up logs sees none of our real strength.

**The caveat, stated rather than buried.** A handicapped ranking is evidence about
the full versions, not proof; depth can change which strategy suits a given
opponent. It is the best evidence obtainable before a counted series and it costs
nothing we were not already spending on a warm-up.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..constants import Role
from .seal_cop import SealCop

#: The configured strength at which a series is a probe. `match_day.py warmup`
#: writes exactly this, so probing needs no flag of its own and a counted run —
#: which `guard_counted_strength` forces to `full` — can never become one.
PROBE_LEVEL = "sandbagged"

#: The uniform weakening. Deliberately a dial no candidate varies, so it cannot
#: erase the differences the probe exists to measure.
HANDICAP: Mapping[str, Mapping[str, Any]] = {
    "cop": {"lookahead": 1},
    "thief": {"horizon": 1},
}


@dataclass(frozen=True)
class Variant:
    """One candidate: a brain class, its dials, and why it is on the list."""

    name: str
    note: str
    dials: Mapping[str, Any] = field(default_factory=dict)
    brain: Any = None          # None means the role's shipped brain


#: Three cops. `pursuit` is what shipped; `walls` is the same brain priced to
#: actually spend its quota — the shipped thresholds were calibrated against
#: near-delta beliefs and score ~0.35 against a real scent-shaped one, which is
#: why two barriers of forty-two were spent in the counted series; `seal` ignores
#: opportunistic walls entirely and builds the halving structure the exact win
#: table prices at eleven barriers.
COPS: tuple[Variant, ...] = (
    Variant("pursuit", "shipped thresholds, barriers only when plainly stalled"),
    Variant("walls", "same brain, barriers priced for a real belief",
            {"barrier_threshold": 0.12, "stalled_threshold": 0.06,
             "stall_patience": 2, "stall_close": 4}),
    Variant("seal", "halve the board, halve the half, chase in the pocket", {}, SealCop),
)

#: Three thieves, all the shipped brain: its fence-blocking and min-cut evasion
#: are measured (64/64 archived cop lines, survives a correct halving cop to step
#: 35) and worth keeping in every candidate. What varies is how much it pays for
#: space against how much it pays for distance.
THIEVES: tuple[Variant, ...] = (
    Variant("safety", "shipped balance of distance and room"),
    Variant("roomy", "pays double for room — the anti-seal posture",
            {"stall_room_weight": 8.0}),
    Variant("tight", "reacts sooner, values room less, stays closer to open ground",
            {"stall_trigger": 1, "stall_room_weight": 2.0}),
)

ROSTER: Mapping[str, tuple[Variant, ...]] = {"cop": COPS, "thief": THIEVES}


def side_of(role: Role) -> str:
    """The roster key for a role."""
    return "cop" if role is Role.COP else "thief"


def probing(strength: str) -> bool:
    """Whether this series is a probe rather than a played-for-keeps run."""
    return str(strength).strip().lower() == PROBE_LEVEL


def for_window(side: str, sub_game: int) -> Variant:
    """The candidate that plays this window.

    Each role holds three of the six windows — 1/3/5 and 2/4/6, whichever way
    round the opening role falls — so integer division maps either set onto the
    roster in order, and the mapping is stable across a replay.
    """
    roster = ROSTER[side]
    return roster[max(int(sub_game) - 1, 0) // 2 % len(roster)]


def by_name(side: str, name: str) -> Variant | None:
    """Look a candidate up by name; `None` when nothing matches."""
    return next((one for one in ROSTER[side] if one.name == str(name)), None)


def dials_for(side: str, variant: Variant, strength: str) -> dict[str, Any]:
    """The dials to build this candidate with, handicapped when probing."""
    dials = dict(variant.dials)
    if probing(strength):
        dials.update(HANDICAP.get(side, {}))
    return dials


def candidate(role: Role, sub_game: int, level: str, opponent: str,
              shipped: Any) -> tuple[Any, dict[str, Any]]:
    """The brain class and extra dials for one window; the shipped brain on doubt.

    A warm-up plays a different candidate per window; a counted run plays the one
    that won this opponent's warm-up. Every failure path — no file, an unreadable
    file, a name retired from the roster — returns the shipped brain with no
    dials, because rule 35 scores a match we could not start as a loss and a
    preference file may not cost us one.
    """
    try:
        from pathlib import Path

        from ..sdk.probe import load_choice

        side = side_of(role)
        chosen = (for_window(side, sub_game) if probing(level)
                  else by_name(side, load_choice(Path.cwd(), opponent, side)))
        if chosen is None:
            return shipped, {}
        return (chosen.brain or shipped), dials_for(side, chosen, level)
    except Exception:  # noqa: BLE001 - never let strategy selection stop a match
        return shipped, {}
