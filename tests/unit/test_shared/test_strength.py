"""One mode, full, always — and the history of how it got that way.

Three levels existed, then the *play* difference was retired on 2026-08-18
(a held-back warm-up cost real games and measured nothing), and the levels
themselves were retired on 2026-08-22 when Naji closed the question: the
modes are supposed to be the same, so there is one. What survives is the
spelling tolerance — a stale config or script saying `sandbagged` must not
stop a match-day agent — and the refusal of unknown values, because a typo
must not quietly mean anything.
"""

import pytest

from najamjad_agent.shared.strength import (
    FULL,
    LEGACY,
    LEVELS,
    StrengthError,
    guard_counted,
    normalise,
    plays_full_strength,
)


def test_every_recognised_spelling_resolves_to_full() -> None:
    """The collapse itself: the legacy names are readable and mean full."""
    for level in LEVELS:
        assert normalise(level) == FULL


def test_an_unknown_level_is_refused_rather_than_defaulting() -> None:
    """A typo must not quietly mean anything, in either direction."""
    with pytest.raises(StrengthError, match="not one of"):
        normalise("strong")
    with pytest.raises(StrengthError):
        normalise("FULL-ish")


def test_the_level_is_read_case_and_whitespace_insensitively() -> None:
    """Config is hand-edited on match day; be forgiving about shape, not spelling."""
    assert normalise("  Full  ") == FULL
    assert normalise("SANDBAGGED") == FULL


def test_an_unset_level_means_full_strength() -> None:
    assert normalise(None) == FULL
    assert normalise("") == FULL


def test_no_level_holds_back() -> None:
    """Reintroducing a held-back level must be a failing test, not a surprise."""
    for level in LEVELS:
        assert plays_full_strength(level), f"{level} must play the shipped policy"


def test_the_guard_validates_and_returns_the_canonical_form() -> None:
    """With one mode the guard has nothing to refuse but a typo — and it still
    refuses that, before a counted match instead of during one."""
    assert guard_counted("  Full ", counted=True) == FULL
    for legacy in LEGACY:
        assert guard_counted(legacy, counted=True) == FULL
    with pytest.raises(StrengthError):
        guard_counted("stronk", counted=True)
