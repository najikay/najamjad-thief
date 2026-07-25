"""Tests for the zero-token template bank and the outbound hint guard."""

import pytest

from najamjad_agent.llm.hint_guard import (
    enforce_word_cap,
    guard_hint,
    strip_coordinates,
)
from najamjad_agent.llm.template_provider import TemplateProvider


def test_the_template_bank_costs_nothing() -> None:
    """Book PAGE 67: a full series may legally be played at zero tokens."""
    completion = TemplateProvider(seed=1).complete("sys", "thief")
    assert completion.usage.total == 0
    assert completion.provider == "template"


def test_the_template_bank_is_always_healthy() -> None:
    """It is the floor the whole chain rests on."""
    assert TemplateProvider().healthy()


def test_hints_use_the_negotiated_map_area() -> None:
    provider = TemplateProvider(map_area="London", seed=3)
    assert "the Thames" in provider.landmarks()
    assert "Times Square" not in provider.landmarks()


def test_an_unknown_map_area_falls_back_to_generic_landmarks() -> None:
    assert "the old bridge" in TemplateProvider(map_area="Atlantis").landmarks()


def test_output_is_deterministic_under_a_seed() -> None:
    """Reproducibility matters for replay and for debugging a lost game."""
    first = TemplateProvider(seed=7).compose("thief")
    again = TemplateProvider(seed=7).compose("thief")
    assert first == again


def test_the_two_roles_speak_differently() -> None:
    thief = TemplateProvider(seed=5).compose("thief")["message"]
    cop = TemplateProvider(seed=5).compose("police")["message"]
    assert thief != cop


def test_hints_respect_the_agreed_word_cap() -> None:
    for seed in range(20):
        composed = TemplateProvider(seed=seed).compose("thief", hint_max_words=6)
        assert len(composed["message"].split()) <= 6


def test_the_lie_rate_comes_from_configuration() -> None:
    """The reference lies a flat 40% — a predictable tell we do not inherit."""
    always = TemplateProvider(lie_probability=1.0, seed=1)
    never = TemplateProvider(lie_probability=0.0, seed=1)
    assert all(always.compose("thief")["verdict"] == "lie" for _ in range(10))
    assert all(never.compose("thief")["verdict"] == "truth" for _ in range(10))


def test_an_impossible_lie_rate_is_refused() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        TemplateProvider(lie_probability=1.5)


def test_the_completion_reports_the_intent_for_sealing() -> None:
    raw = TemplateProvider(seed=2).complete("sys", "thief agent").raw
    assert raw["verdict"] in ("truth", "lie")


@pytest.mark.parametrize(
    "leak",
    [
        "I am at (3,4) right now",
        "moving to 5,6 quickly",
        "currently row 3 heading north",
        "hiding in cell 12",
        "waiting at square 4",
    ],
)
def test_coordinate_leaks_are_stripped(leak: str) -> None:
    """Book rule 27: a numeric-position protocol would break the whole game."""
    cleaned, found = strip_coordinates(leak)
    assert found
    assert not any(character.isdigit() for character in cleaned)


def test_ordinary_prose_is_left_alone() -> None:
    text = "Slipping past the Brooklyn Bridge while you look away."
    cleaned, found = strip_coordinates(text)
    assert not found
    assert cleaned == text


def test_the_word_cap_trims_only_when_needed() -> None:
    assert enforce_word_cap("one two three", 5) == ("one two three", False)
    assert enforce_word_cap("one two three four", 2) == ("one two", True)


def test_a_clean_hint_passes_untouched() -> None:
    result = guard_hint("Circling the waterfront tonight.", "lie")
    assert result.clean
    assert result.intent == "lie"


def test_a_leaking_hint_is_cleaned_and_reported() -> None:
    """The guard is a guarantee; the prompt was only a request."""
    result = guard_hint("I am at (3,4) near the docks", "truth")
    assert "(3,4)" not in result.text
    assert not result.clean
    assert any("rule 27" in problem for problem in result.problems)


def test_an_over_long_hint_is_trimmed_to_the_agreed_limit() -> None:
    result = guard_hint(" ".join(["word"] * 30), "truth", hint_max_words=15)
    assert len(result.text.split()) == 15
    assert any("15-word limit" in problem for problem in result.problems)


def test_an_empty_hint_becomes_a_neutral_line() -> None:
    """Silence is not an option — the opponent expects free-language dialogue."""
    result = guard_hint("", "truth")
    assert result.text
    assert any("empty hint" in problem for problem in result.problems)


def test_a_hint_that_was_entirely_coordinates_still_yields_prose() -> None:
    result = guard_hint("(3,4)", "truth")
    assert result.text
    assert any("nothing survived" in problem for problem in result.problems)


def test_an_invalid_intent_is_sealed_as_truth() -> None:
    """Intent is cryptographically sealed, so it must be a legal value."""
    result = guard_hint("Heading uptown.", "maybe")
    assert result.intent == "truth"
    assert any("not truth/lie" in problem for problem in result.problems)


def test_every_template_hint_survives_the_guard() -> None:
    """Our own floor must never trip our own outbound rules."""
    for seed in range(25):
        composed = TemplateProvider(seed=seed).compose("thief")
        assert guard_hint(composed["message"], composed["verdict"]).clean
