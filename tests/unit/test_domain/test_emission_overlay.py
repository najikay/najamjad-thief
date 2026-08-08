"""Two dials, reachable one at a time (T-2534).

`--quiet` set scent *and* hints off together and `--talk` set both on, so the
middle ground existed in `EmissionPolicy` and in `config/<role>/game.toml` and
could not be asked for on a command line. That is the two-switch setup this
project has lost games to before: a mode you can only reach by hand-editing a
tracked file minutes before a match is a mode nobody reaches correctly.

The middle ground is not hypothetical. uoh-ay26 sent a hint on every one of 135
sealed records across six mini-games and **not one scent cell**, so mirroring
them needs `--scent none --hints` — which no combination of `--quiet`/`--talk`
could express, while `--talk` handed them the scent field they were withholding
from us.
"""

import pytest

from najamjad_agent.domain.emission import (
    EmissionError,
    EmissionPolicy,
    ScentEmission,
    emission_overlay,
)


def test_a_bare_command_changes_nothing() -> None:
    """No flags must leave the shipped config in charge.

    An overlay of `{"emission": {}}` would also be falsy, but returning it
    invites a caller to apply an empty section and quietly re-anchor defaults.
    """
    assert emission_overlay() == {}


def test_quiet_still_silences_both_halves() -> None:
    """The preset people already use must not change meaning underneath them."""
    assert emission_overlay(quiet=True) == {"emission": {"scent": "none", "hint": False}}


def test_talk_is_the_absence_of_a_choice_not_a_choice() -> None:
    """`--talk` is the default, so it must not overlay anything.

    If it wrote `{"scent": "full"}` it would override a config that had
    deliberately set `window`, which is the opposite of what a default does.
    """
    assert emission_overlay(quiet=False) == {}


def test_the_case_that_made_this_necessary() -> None:
    """Mirror a peer who speaks but emits nothing — uoh-ay26, all six games."""
    assert emission_overlay(scent="none", hints=True) == {
        "emission": {"scent": "none", "hint": True}
    }


def test_an_explicit_flag_beats_the_preset() -> None:
    """`--quiet --hints` is a request, not a contradiction to reject.

    Rejecting it would be defensible and useless: the operator has said exactly
    what they want, and the narrower reading costs a match to make a point.
    """
    assert emission_overlay(quiet=True, hints=True)["emission"]["hint"] is True
    assert emission_overlay(quiet=True, scent="full")["emission"]["scent"] == "full"


def test_each_dial_moves_alone() -> None:
    """The whole point: one dial set must not imply the other."""
    assert emission_overlay(scent="window") == {"emission": {"scent": "window"}}
    assert emission_overlay(hints=False) == {"emission": {"hint": False}}


def test_hints_false_is_not_confused_with_hints_unset() -> None:
    """`None` means "not asked"; `False` means "send none". A bool cannot say both.

    This is why the option is `bool | None` rather than `bool`: a plain default
    of `False` would silence hints on every bare command.
    """
    assert "hint" not in emission_overlay(hints=None).get("emission", {})
    assert emission_overlay(hints=False)["emission"]["hint"] is False


def test_the_mode_is_normalised_the_way_the_config_reader_normalises_it() -> None:
    """`from_config` lowercases and strips; an overlay must arrive the same."""
    assert emission_overlay(scent="  NONE ")["emission"]["scent"] == "none"


@pytest.mark.parametrize("mode", [each.value for each in ScentEmission])
def test_every_mode_the_policy_accepts_survives_the_overlay(mode: str) -> None:
    """The round trip that matters: flag -> overlay -> policy.

    Asserted against `from_config` rather than against a literal, so a new mode
    added to `ScentEmission` is covered here without touching this test.
    """
    section = emission_overlay(scent=mode)["emission"]

    assert EmissionPolicy.from_config(section).scent_mode is ScentEmission(mode)


def test_an_unknown_mode_is_refused_by_the_reader_not_silently_dropped() -> None:
    """We deliberately do not validate here — one list, one owner.

    Duplicating the allowed values in the overlay builder is how the two get to
    disagree; `from_config` already refuses by name and says which values are
    legal. This pins that a typo still fails, and fails informatively.
    """
    section = emission_overlay(scent="quiet")["emission"]

    with pytest.raises(EmissionError, match="not one of"):
        EmissionPolicy.from_config(section)
