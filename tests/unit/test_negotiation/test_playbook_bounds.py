"""Red lines have to hold in both directions, and ours only held in one.

`Position.acceptable` checked a floor and nothing else, so every timing term was
refused for being too small and accepted at any size: we would have signed a
**600-second response timeout** and a **900-second watchdog**. Rule 12 forbids
lowering an Appendix F minimum and permits raising one, so those signatures
would have been perfectly legal — and a straight competitive loss.

Our agent decides in about ten milliseconds. A peer who wants minutes per move
wants them to run a model in. The module docstring already declines the LLM-move
exception for exactly that reason; a timing term is the same concession wearing
a different hat.
"""

from najamjad_agent.negotiation.playbook import POSITIONS

BY_KEY = {position.key: position for position in POSITIONS}


def test_the_book_minimum_is_still_a_floor() -> None:
    """Rule 12: minimums may be raised by agreement, never lowered."""
    assert not BY_KEY["response_timeout_sec"].acceptable(20)
    assert not BY_KEY["watchdog_timeout_sec"].acceptable(30)


def test_a_peer_cannot_buy_itself_thinking_time() -> None:
    """The hole. Ten minutes a move used to be a value we would sign."""
    assert not BY_KEY["response_timeout_sec"].acceptable(600)
    assert not BY_KEY["watchdog_timeout_sec"].acceptable(900)


def test_the_book_value_itself_is_always_acceptable() -> None:
    """A red line that refused Table 19's own numbers would forfeit matches.

    We need two counted matches against different teams. Being unplayable is a
    worse outcome than any term on this list.
    """
    for key in ("response_timeout_sec", "watchdog_timeout_sec", "hint_max_words"):
        position = BY_KEY[key]
        assert position.acceptable(position.default), key


def test_we_no_longer_volunteer_extra_time() -> None:
    """We used to *prefer* 45 s, i.e. offer the advantage unprompted.

    A tunnel hiccup is a real problem, and retries plus the send deadline are a
    better answer to it than lengthening every turn of the match for both sides.
    """
    assert BY_KEY["response_timeout_sec"].preferred == 30
    assert BY_KEY["watchdog_timeout_sec"].preferred == 60


def test_a_small_courtesy_is_still_possible() -> None:
    """Bounded, not stubborn — the ceiling is a red line, not a refusal to move.

    45 s is what we were previously willing to volunteer, so accepting up to it
    concedes nothing we had not already offered, and it leaves room to settle a
    handshake rather than lose a match over fifteen seconds.
    """
    assert BY_KEY["response_timeout_sec"].acceptable(45)
    assert BY_KEY["watchdog_timeout_sec"].acceptable(90)


def test_the_hint_cap_cannot_be_raised_into_an_essay() -> None:
    """`hint_max_words` is a cap, so raising it weakens the book.

    It had no bound at all, so a peer could have proposed 500-word hints — more
    room to leak, and more room to reason.
    """
    assert BY_KEY["hint_max_words"].acceptable(15)
    assert not BY_KEY["hint_max_words"].acceptable(40)


def test_terms_the_book_fixes_are_unmoved() -> None:
    """The fixed rows must not have been loosened by adding a ceiling."""
    for key in ("grid_size", "max_barriers", "max_moves", "num_games"):
        position = BY_KEY[key]
        assert position.acceptable(position.default), key
        assert not position.acceptable(float(position.default) - 1), key
