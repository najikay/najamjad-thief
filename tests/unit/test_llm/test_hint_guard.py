"""The last gate before a hint leaves us — and what it used to let through.

`guard_hint` strips coordinates (rule 27) and enforces the agreed word cap.
Neither has any opinion about *syntax*, so a provider that answered with JSON
went out as a hint, was sealed into our commit-reveal record, and landed in an
audited log.
"""

from najamjad_agent.llm.hint_guard import guard_hint, looks_like_machinery


def test_a_plain_hint_passes_untouched() -> None:
    """The ordinary case, so the additions below cannot be the whole file."""
    plain = "Taking the long way round by the waterfront."

    result = guard_hint(plain, "truth")

    assert result.text == plain
    assert result.intent == "truth"
    assert not result.problems


def test_machinery_is_recognised_by_shape_not_by_content() -> None:
    """Leading brace or bracket, or a quoted key before a colon."""
    assert looks_like_machinery('{"message": "New')
    assert looks_like_machinery('["north", "east"]')
    assert not looks_like_machinery("Heading north: the park is behind me.")


def test_model_syntax_never_reaches_the_wire() -> None:
    """The literal hint we sent in a real match, and must not send again.

    Mini-game 2 against Amjad carries `{"message": "New` as a sealed hint — a
    provider answered with JSON, or with JSON truncated in transit, and we
    sealed it and sent it. It is now in an audited log a grader reads and in our
    own commit-reveal record, where it cannot be edited out.

    Nothing upstream had an opinion about it: `strip_coordinates` removes
    digits, `enforce_word_cap` counts words, and a three-token fragment passes a
    fifteen-word cap comfortably.
    """
    result = guard_hint('{"message": "New', "truth")

    assert not result.text.startswith("{")
    assert any("model syntax" in problem for problem in result.problems)


def test_a_whole_json_reply_is_rejected_too() -> None:
    """Not only the truncated case — the intact one is just as unsendable."""
    assert guard_hint('{"intent": "lie", "hint": "by the bridge"}', "lie").text.startswith(
        "Still moving"
    )
    assert guard_hint('["north", "east"]', "truth").text.startswith("Still moving")


def test_ordinary_english_with_a_colon_survives() -> None:
    """The check must be narrow, or it eats the hints we want to send.

    A colon is ordinary punctuation. Only a leading brace or bracket, or a
    quoted key followed by a colon, is machinery.
    """
    kept = "Heading north: the park is behind me."

    assert guard_hint(kept, "truth").text == kept
