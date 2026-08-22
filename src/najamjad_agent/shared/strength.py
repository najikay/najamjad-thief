"""How hard we play: one mode, full, always.

There used to be three levels — `full`, `practice`, and a documented
`sandbagged` for warm-ups — and the split cost more than it bought. The
sandbag switch spent most of its life broken in one direction or another: for
weeks `_tuning` never delivered the level to the brains at all, so every
"sandbagged" warm-up played at full strength while we believed otherwise; and
when it *did* work, a warm-up measured a policy we would never play in a
counted series, which is a number about nothing (the probe machinery built on
top of it was retired the same day as the levels). Naji closed the question
on 2026-08-22: the modes are supposed to be the same now, so there is one.

The vocabulary survives for compatibility — configs, scripts and opponent
correspondence say `strength.level = "full"` — and the old level names are
still *accepted* so a stale config cannot crash an agent on match day; they
all mean full. What is still refused is an unknown value: a typo must not
quietly mean anything (the same reasoning `EmissionPolicy.from_config`
gives). Practice-vs-counted is not a strength question and never was — it is
`email.mode` and the practice banner, owned by `shared/practice.py`.
"""

from __future__ import annotations

FULL = "full"
#: Retired levels, still readable so a stale config or an old script cannot
#: stop a match. Every one of them now plays exactly the same game.
LEGACY = ("practice", "sandbagged")

LEVELS = (FULL, *LEGACY)


class StrengthError(ValueError):
    """Raised when a strength setting is not a recognised spelling."""


def normalise(value: object) -> str:
    """Read a configured level; every recognised spelling resolves to full."""
    level = str(value or FULL).strip().lower()
    if level not in LEVELS:
        raise StrengthError(f"strength {level!r} is not one of {list(LEVELS)}")
    return FULL


def plays_full_strength(level: object) -> bool:
    """Always true for any recognised level — kept for its callers' clarity."""
    return normalise(level) == FULL


def guard_counted(level: object, counted: bool) -> str:
    """Validate the configured level; with one mode there is nothing to refuse.

    Kept because the call sites (`sdk/config_overrides.guard_counted_strength`
    and the bootstrap) are the places a *typo* still surfaces before a counted
    match instead of during one.
    """
    del counted
    return normalise(level)
