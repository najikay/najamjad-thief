"""How hard we play, as one named setting.

Three levels, and the naming is deliberate rather than coy:

* **`full`** — everything we have. The only level a counted match may use.
* **`practice`** — full strength, but in a practice run. For rehearsing the
  machinery against a real peer without the result counting.
* **`sandbagged`** — deliberately weakened, for uncounted warm-ups.

**On `sandbagged`, plainly.** Warm-up games are uncounted by the book's own
design, and holding back in a friendly is ordinary competitive practice — a
team that sees an unbeatable agent in a warm-up may decline the counted series,
and rule 31 makes a declined series more expensive than a lost one. Deception
inside this game is also an intended mechanic; `llm/hint_policy.py` exists to
decide when to lie.

What it must never be is hidden. These repositories are shared with the
lecturer under rule 49, so this file *will* be read. A clearly named, documented
setting reads as the tactical choice it is; the same behaviour behind a vague
name reads as something we were concealing, which is worse than not doing it.
Counted matches are played at `full`, and the guard below makes that mechanical
rather than a thing to remember at 20:00.

`sandbagged` reuses our own previous policy rather than inventing a weak one:
the thief falls back to the weighted-sum objective that actually lost three
games to uoh-sqak. That is credible precisely because it *was* us, and it needs
no separate brain to maintain.
"""

from __future__ import annotations

FULL = "full"
PRACTICE = "practice"
SANDBAGGED = "sandbagged"

LEVELS = (FULL, PRACTICE, SANDBAGGED)

#: Levels at which the brains play everything they have.
AT_FULL_STRENGTH = frozenset({FULL, PRACTICE})


class StrengthError(ValueError):
    """Raised when a counted match is armed at anything but full strength."""


def normalise(value: object) -> str:
    """Read a configured level, refusing anything not on the list.

    An unknown level must not quietly mean `full`: a typo would then be
    invisible in the one direction that matters, and a typo in the *other*
    direction would hand a counted match away.
    """
    level = str(value or FULL).strip().lower()
    if level not in LEVELS:
        raise StrengthError(f"strength {level!r} is not one of {list(LEVELS)}")
    return level


def plays_full_strength(level: object) -> bool:
    """Whether the brains should use everything at this level."""
    return normalise(level) in AT_FULL_STRENGTH


def guard_counted(level: object, counted: bool) -> str:
    """Refuse to start a counted match at less than full strength.

    Modelled on the `email.mode` draft trap, and for the same reason: the
    expensive mistake is not choosing wrongly, it is *forgetting* — arming a
    warm-up and then playing the counted series without re-arming. A counted
    match played sandbagged throws away real league points and cannot be
    replayed, so this raises rather than warns.
    """
    resolved = normalise(level)
    if counted and resolved != FULL:
        raise StrengthError(
            f"a counted match must be played at {FULL!r}, not {resolved!r}; "
            f"set strength.level = \"{FULL}\" (or pass --strength {FULL})"
        )
    return resolved
