"""Tests for how much of our own evidence crosses the wire."""

import pytest

from najamjad_agent.domain.emission import (
    EmissionError,
    EmissionPolicy,
    ScentEmission,
)

#: A cumulative field of the shape our thief actually emitted against uoh-sqak:
#: a 5x5 deposit around (5,5) plus a stale tail from cells it visited earlier.
FIELD = {
    **{f"{row},{col}": 0.9 if (row, col) == (5, 5) else 0.2 for row in (3, 4, 5, 6) for col in (3, 4, 5, 6)},
    "0,0": 0.05,
    "1,1": 0.08,
    "2,2": 0.11,
}


def test_the_default_sends_everything_it_always_did() -> None:
    """A default that changes behaviour silently is the one unacceptable default."""
    policy = EmissionPolicy()

    assert policy.scent_mode is ScentEmission.FULL
    assert policy.hints is True
    assert policy.scent(FIELD, (5, 5)) == FIELD


def test_window_mode_keeps_only_the_agreed_grid_around_us() -> None:
    """`pheromone_grid_size: 5` is a 5x5, so Chebyshev radius 2."""
    emitted = EmissionPolicy(ScentEmission.WINDOW, grid_size=5).scent(FIELD, (5, 5))

    assert "3,3" in emitted, "inside the window"
    assert "0,0" not in emitted, "a stale tail four cells away"
    assert "2,2" not in emitted


def test_window_mode_transmits_the_real_decayed_values() -> None:
    """It clips the true field; it does not synthesise a fresh deposit.

    That is what keeps `window` a reading of the agreed term rather than
    different physics — every value sent is still a true statement.
    """
    emitted = EmissionPolicy(ScentEmission.WINDOW).scent(FIELD, (5, 5))

    assert emitted["5,5"] == FIELD["5,5"]
    assert emitted["4,4"] == FIELD["4,4"]


def test_window_mode_still_leaks_our_exact_cell() -> None:
    """Stated as a test because it is the reason `window` is not a hiding place.

    The centre of a deposit is the agreed centre intensity and is the unique
    maximum, so argmax reads our position whatever the window size.
    """
    emitted = EmissionPolicy(ScentEmission.WINDOW).scent(FIELD, (5, 5))

    assert max(emitted, key=lambda key: emitted[key]) == "5,5"


def test_none_mode_sends_an_empty_map_not_a_missing_field() -> None:
    """The reference parser rejects a message whose declared fields are absent.

    A turn it cannot read is a turn we forfeit, which costs more than emitting.
    """
    emitted = EmissionPolicy(ScentEmission.NONE).scent(FIELD, (5, 5))

    assert emitted == {}
    assert isinstance(emitted, dict)


def test_hints_are_spoken_by_default_and_silenced_on_request() -> None:
    assert EmissionPolicy().hint("Slipping past Times Square") == "Slipping past Times Square"
    assert EmissionPolicy(hints=False).hint("Slipping past Times Square") == ""


def test_config_reads_each_mode() -> None:
    assert EmissionPolicy.from_config({"scent": "none"}).scent_mode is ScentEmission.NONE
    assert EmissionPolicy.from_config({"scent": "WINDOW"}).scent_mode is ScentEmission.WINDOW
    assert EmissionPolicy.from_config({"hint": False}).hints is False


def test_config_defaults_to_full_when_the_section_is_absent() -> None:
    assert EmissionPolicy.from_config(None) == EmissionPolicy()


def test_an_unknown_mode_is_refused_rather_than_defaulted() -> None:
    """A typo must not be invisible in the direction that changes how we play."""
    with pytest.raises(EmissionError, match="is not one of"):
        EmissionPolicy.from_config({"scent": "quiet"})


def test_the_window_follows_the_negotiated_grid_size() -> None:
    """A renegotiated `pheromone_grid_size` must move the window with it."""
    wide = EmissionPolicy(ScentEmission.WINDOW, grid_size=7).scent(FIELD, (5, 5))

    assert "2,2" in wide, "radius 3 reaches three cells out"


def test_a_malformed_key_is_dropped_rather_than_crashing_the_turn() -> None:
    emitted = EmissionPolicy(ScentEmission.WINDOW).scent({"not-a-cell": 0.5}, (5, 5))

    assert emitted == {}


def test_the_declaration_names_what_we_are_doing() -> None:
    """Emitting less is a tactical choice, and not a secret one (rule 49)."""
    declared = EmissionPolicy(ScentEmission.NONE, hints=False).as_declaration()

    assert declared == {"scent": "none", "hint": "silent"}


def test_reciprocity_is_off_by_default() -> None:
    """Going quiet is a choice to make deliberately, not one that happens to us."""
    assert EmissionPolicy().reciprocal is False
    assert EmissionPolicy.from_config({}).reciprocal is False


def test_a_talking_peer_is_answered_normally() -> None:
    policy = EmissionPolicy(reciprocal=True)

    assert policy.mirroring(peer_silent=False) is policy


def test_a_silent_peer_is_mirrored_exactly() -> None:
    """As quiet as they are and no quieter — that is what makes it reciprocal."""
    mirrored = EmissionPolicy(reciprocal=True).mirroring(peer_silent=True)

    assert mirrored.scent_mode is ScentEmission.NONE
    assert mirrored.hints is False
    assert mirrored.scent(FIELD, (5, 5)) == {}
    assert mirrored.hint("Times Square") == ""


def test_silence_is_not_mirrored_unless_reciprocity_is_enabled() -> None:
    """Off means off, however quiet they are."""
    policy = EmissionPolicy(reciprocal=False)

    assert policy.mirroring(peer_silent=True) is policy


def test_the_negotiated_grid_size_survives_mirroring() -> None:
    """Mirroring changes what we send, never the agreed physics behind it."""
    mirrored = EmissionPolicy(reciprocal=True, grid_size=7).mirroring(peer_silent=True)

    assert mirrored.grid_size == 7


def test_config_reads_the_reciprocal_flag() -> None:
    assert EmissionPolicy.from_config({"reciprocal": True}).reciprocal is True
