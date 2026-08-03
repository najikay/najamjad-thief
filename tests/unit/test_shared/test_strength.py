"""Tests for the play-strength setting and its counted-match guard.

The expensive mistake this exists to prevent is not choosing wrongly, it is
*forgetting* — arming a sandbagged warm-up and then playing the counted series
without re-arming. A counted match played weak throws away real league points
and cannot be replayed, which is the same shape as the `email.mode` draft trap
that nearly shipped.
"""

import pytest

from najamjad_agent.shared.strength import (
    FULL,
    LEVELS,
    PRACTICE,
    SANDBAGGED,
    StrengthError,
    guard_counted,
    normalise,
    plays_full_strength,
)


def test_a_counted_match_refuses_to_start_sandbagged() -> None:
    """The whole point: this raises rather than warns."""
    with pytest.raises(StrengthError, match="counted match"):
        guard_counted(SANDBAGGED, counted=True)


def test_a_counted_match_refuses_practice_strength_too() -> None:
    """`practice` is full strength but the wrong mode; a counted run is neither."""
    with pytest.raises(StrengthError):
        guard_counted(PRACTICE, counted=True)


def test_a_counted_match_at_full_strength_is_allowed() -> None:
    assert guard_counted(FULL, counted=True) == FULL


def test_an_uncounted_match_may_be_played_at_any_level(level=None) -> None:
    for level in LEVELS:
        assert guard_counted(level, counted=False) == level


def test_an_unknown_level_is_refused_rather_than_defaulting() -> None:
    """A typo must not quietly mean `full`, in either direction.

    Silently defaulting would hide the mistake exactly where it costs most: a
    misspelt level either hands a counted match away or plays a warm-up at full
    strength after we told an opponent otherwise.
    """
    with pytest.raises(StrengthError, match="not one of"):
        normalise("strong")
    with pytest.raises(StrengthError):
        normalise("FULL-ish")


def test_the_level_is_read_case_and_whitespace_insensitively() -> None:
    """Config is hand-edited on match day; be forgiving about shape, not spelling."""
    assert normalise("  Full  ") == FULL
    assert normalise("SANDBAGGED") == SANDBAGGED


def test_an_unset_level_means_full_strength() -> None:
    """The safe default is the strong one; weakness must be asked for."""
    assert normalise(None) == FULL
    assert normalise("") == FULL


def test_only_the_sandbagged_level_holds_back() -> None:
    assert plays_full_strength(FULL)
    assert plays_full_strength(PRACTICE)
    assert not plays_full_strength(SANDBAGGED)


def test_the_guard_returns_the_normalised_level_for_the_caller() -> None:
    """Callers store what the guard returned, so it must be the canonical form."""
    assert guard_counted("  Full ", counted=True) == FULL
