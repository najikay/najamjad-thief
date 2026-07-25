"""Tests for prompt builders and the deterministic-first hint parser."""

import json

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.llm.hint_parser import (
    extract_json,
    local_confidence,
    parse_locally,
    parse_model_reply,
)
from najamjad_agent.llm.prompts import (
    hint_prompt,
    negotiate_prompt,
    parse_prompt,
    prompt_catalogue,
)

LANDMARKS = {"Times Square": (2, 3), "the Brooklyn Bridge": (5, 5)}


def test_the_hint_prompt_pins_arena_and_word_cap() -> None:
    system, _ = hint_prompt("thief", "New York", 15, "truth")
    assert "New York" in system
    assert "15 words" in system


def test_the_hint_prompt_forbids_coordinates() -> None:
    """The prompt asks; hint_guard enforces. Both are needed (rule 27)."""
    system, _ = hint_prompt("police", "London", 15, "truth")
    assert "never numbers, coordinates" in system


def test_the_hint_prompt_demands_the_strict_json_contract() -> None:
    system, _ = hint_prompt("thief", "", 15, "lie")
    assert '"message"' in system and '"verdict"' in system and '"reasoning"' in system


def test_the_hint_prompt_carries_our_chosen_intent() -> None:
    """We decide truth or lie; the model only writes the words."""
    _, lying = hint_prompt("thief", "", 15, "lie")
    _, honest = hint_prompt("thief", "", 15, "truth")
    assert "Mislead" in lying
    assert "true" in honest


def test_the_two_roles_get_different_framing() -> None:
    thief, _ = hint_prompt("thief", "", 15, "truth")
    police, _ = hint_prompt("police", "", 15, "truth")
    assert "evading" in thief and "pursuit" in police


def test_an_empty_arena_still_produces_a_usable_prompt() -> None:
    system, _ = hint_prompt("thief", "", 15, "truth")
    assert "unnamed city" in system


def test_the_parse_prompt_requires_confidence_and_allows_null() -> None:
    """Refusing to guess is the point — null beats an invented direction."""
    system, user, _ = parse_prompt("I am heading north")
    assert "confidence" in system
    assert "Never guess" in system
    assert "heading north" in user


def test_the_negotiate_prompt_carries_position_and_red_lines() -> None:
    system, user = negotiate_prompt({"grid_size": 7}, {"llm_moves": "we decline"}, "rival")
    assert "grid_size" in user and "llm_moves" in user
    assert "rival" in user
    assert "red line" in system.lower()


def test_the_negotiate_prompt_keeps_binding_numbers_out_of_prose() -> None:
    """Nothing binding may live only in free text where a model could round it."""
    system, _ = negotiate_prompt({"grid_size": 7}, {})
    assert "structured block" in system


def test_the_catalogue_exposes_every_prompt_for_the_prompt_book() -> None:
    catalogue = prompt_catalogue()
    assert set(catalogue) == {"hint", "parse", "negotiate"}
    assert all(text.strip() for text in catalogue.values())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I am heading north past the park", Move.NORTH),
        ("moving south quickly", Move.SOUTH),
        ("slipping east along the water", Move.EAST),
        ("cutting west through alleys", Move.WEST),
        ("holding position for now", Move.STAY),
        ("going uptown", Move.NORTH),
        ("headed downtown", Move.SOUTH),
    ],
)
def test_plain_directions_parse_without_a_model(text: str, expected: Move) -> None:
    """Most hints are plainly worded — a free local parse handles them."""
    assert parse_locally(text).direction is expected


def test_landmarks_are_recognised_locally() -> None:
    claim = parse_locally("slipping past Times Square", LANDMARKS)
    assert claim.landmark_cells == ((2, 3),)


def test_an_uninformative_hint_yields_no_claim() -> None:
    claim = parse_locally("you will never catch me")
    assert not claim.is_informative
    assert local_confidence(claim, "you will never catch me") == 0.0


def test_a_directional_claim_is_trusted_more_than_a_landmark() -> None:
    directional = parse_locally("heading north")
    landmark = parse_locally("near Times Square", LANDMARKS)
    assert local_confidence(directional, "heading north") > local_confidence(
        landmark, "near Times Square"
    )


def test_a_negated_hint_lowers_local_confidence() -> None:
    """'I did NOT go north' means the opposite of what the keyword suggests."""
    text = "I did not go north at all"
    claim = parse_locally(text)
    assert local_confidence(claim, text) == pytest.approx(0.2)


def test_the_model_reply_is_parsed_with_its_confidence() -> None:
    reply = json.dumps({"direction": "south", "landmarks": ["Times Square"], "confidence": 0.9})
    claim, confidence = parse_model_reply(reply, LANDMARKS)
    assert claim.direction is Move.SOUTH
    assert claim.landmark_cells == ((2, 3),)
    assert confidence == 0.9


def test_a_fenced_model_reply_is_still_read() -> None:
    reply = '```json\n{"direction": "east", "landmarks": [], "confidence": 0.6}\n```'
    claim, confidence = parse_model_reply(reply)
    assert claim.direction is Move.EAST
    assert confidence == 0.6


def test_a_null_direction_is_respected_not_guessed() -> None:
    claim, confidence = parse_model_reply('{"direction": null, "landmarks": [], "confidence": 0.1}')
    assert claim.direction is None
    assert confidence == 0.1


def test_unparseable_model_output_yields_zero_confidence() -> None:
    """A fabricated direction would poison belief with false certainty."""
    claim, confidence = parse_model_reply("sorry, I cannot tell")
    assert not claim.is_informative
    assert confidence == 0.0


def test_a_nonsense_confidence_is_clamped() -> None:
    _, confidence = parse_model_reply('{"direction": "north", "confidence": "very sure"}')
    assert confidence == 0.0
    _, high = parse_model_reply('{"direction": "north", "confidence": 5}')
    assert high == 1.0


def test_unknown_landmarks_in_a_reply_are_dropped() -> None:
    claim, _ = parse_model_reply('{"direction": null, "landmarks": ["Atlantis"]}', LANDMARKS)
    assert claim.landmark_cells == ()


def test_extract_json_handles_chatty_and_empty_replies() -> None:
    assert extract_json('Here you go: {"a": 1}') == {"a": 1}
    assert extract_json("") is None
    assert extract_json("no json here") is None
    assert extract_json("[1, 2]") is None


def test_situation_context_is_included_when_supplied() -> None:
    """The model writes better bluffs when it knows the shape of the turn."""
    _, user = hint_prompt("thief", "New York", 15, "lie", context={"step": 4, "pressure": "high"})
    assert "step" in user and "pressure" in user
