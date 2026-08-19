"""An agreement we accepted must start the window it names (anrbj666, g03).

Our server answered their negotiate `accepted: true` and then nothing began,
because `exchange_agreement` only reached its `receive` after its `send`
returned. Our send raised — their cop and thief run as two processes on two
doors, and at the start of a window we still hold the door their *previous*
role answered on — so the attempt was scored a failure with their signed terms
sitting unread in our inbox.

Alon named it first and named it right: "accept-without-start killed g03,
advance-past-unplayed turned it fatal." This is the first of the three.
"""

import pytest

from najamjad_agent.negotiation.contract import Contract
from najamjad_agent.negotiation.handshake import HandshakeError, exchange_agreement

TERMS = {"board_size": 7, "num_games": 6}
OURS = {"sub_game_number": 3, "role": "police"}


def their_agreement(sub_game: int | None = 3, terms: dict | None = None) -> dict:
    """What a peer's negotiate looks like once our inbox has validated it."""
    signed = Contract(dict(terms or TERMS)).signed()
    return signed if sub_game is None else {**signed, "sub_game_number": sub_game}


def inbox(*messages: dict):
    """A `receive` over a queue that empties, like the real one."""
    waiting = list(messages)

    def receive(_timeout):
        return waiting.pop(0) if waiting else None

    return receive


def refuses(_payload):
    """Their door for this role is not the one we are holding yet."""
    raise ConnectionError("All connection attempts failed")


def test_the_window_starts_on_their_agreement_when_ours_cannot_be_sent() -> None:
    """The whole fix: a failed announcement is not a failed window."""
    events: list[dict] = []

    peer = exchange_agreement(
        terms=TERMS, identity={}, declarations=dict(OURS),
        send=refuses, receive=inbox(their_agreement()), emit=events.append,
    )

    assert peer["terms"] == TERMS
    names = [event["event"] for event in events]
    assert "handshake.inbound_first" in names
    assert "handshake.locked" in names, "adopted agreements are locked like any other"


def test_a_shut_gate_can_mean_they_started_the_window_without_us() -> None:
    """The politest form of the same failure, and the likeliest one.

    They handshook us, our server accepted, they opened the mini-game — so when
    we finally dial them their gate is shut and they answer "busy, ask again at
    the boundary". Waiting for that boundary waits for a game we are supposed to
    be playing, while they time out on a first turn we never send.
    """
    from najamjad_agent.net.match_gate import BUSY_REASON

    busy = {"accepted": False, "errors": [BUSY_REASON]}
    events: list[dict] = []

    peer = exchange_agreement(
        terms=TERMS, identity={}, declarations=dict(OURS),
        send=lambda _payload: busy, receive=inbox(their_agreement()), emit=events.append,
    )

    assert peer["terms"] == TERMS
    assert "handshake.locked" in [event["event"] for event in events]


def test_a_gate_shut_over_someone_elses_window_is_still_a_refusal() -> None:
    """Only an agreement naming OUR window may start it (rules 33-35)."""
    from najamjad_agent.negotiation.handshake import HandshakeBusyError
    from najamjad_agent.net.match_gate import BUSY_REASON

    with pytest.raises(HandshakeBusyError):
        exchange_agreement(
            terms=TERMS, identity={}, declarations=dict(OURS),
            send=lambda _payload: {"accepted": False, "errors": [BUSY_REASON]},
            receive=inbox(their_agreement(sub_game=2)),
        )


def test_an_empty_inbox_re_raises_our_own_error() -> None:
    """The retry loop classifies on the exception type, so it must survive.

    A `ConnectionError` rewritten into a `HandshakeError` here would be spent
    from the ordinary budget instead of the generous window budget, which is
    the misclassification that let us give up on a peer who was merely late.
    """
    with pytest.raises(ConnectionError):
        exchange_agreement(
            terms=TERMS, identity={}, declarations=dict(OURS),
            send=refuses, receive=inbox(),
        )


def test_an_agreement_for_a_different_window_is_refused() -> None:
    """Adopting it is how one game acquires two `sub_game_number`s (rules 33-35)."""
    events: list[dict] = []

    with pytest.raises(ConnectionError):
        exchange_agreement(
            terms=TERMS, identity={}, declarations=dict(OURS),
            send=refuses, receive=inbox(their_agreement(sub_game=5)), emit=events.append,
        )

    mismatch = [event for event in events if event["event"] == "handshake.window_mismatch"]
    assert mismatch and (mismatch[0]["ours"], mismatch[0]["theirs"]) == (3, 5)


def test_a_stale_agreement_does_not_block_the_next_peek() -> None:
    """It is dropped, not put back: the queue only pops, so a kept one poisons
    every future attempt against a peer who re-sends per window anyway."""
    receive = inbox(their_agreement(sub_game=5), their_agreement(sub_game=3))

    with pytest.raises(ConnectionError):
        exchange_agreement(terms=TERMS, identity={}, declarations=dict(OURS),
                           send=refuses, receive=receive)
    peer = exchange_agreement(terms=TERMS, identity={}, declarations=dict(OURS),
                              send=refuses, receive=receive)

    assert peer["sub_game_number"] == 3


def test_a_peer_that_declares_no_window_is_still_played() -> None:
    """Omission has never been a refusal on either side of this protocol."""
    peer = exchange_agreement(
        terms=TERMS, identity={}, declarations=dict(OURS),
        send=refuses, receive=inbox(their_agreement(sub_game=None)),
    )

    assert peer["terms"] == TERMS


def test_their_terms_are_verified_exactly_as_on_the_ordinary_path() -> None:
    """A window that starts unverified is worse than one that does not start."""
    with pytest.raises(HandshakeError, match="different terms"):
        exchange_agreement(
            terms=TERMS, identity={}, declarations=dict(OURS),
            send=refuses, receive=inbox(their_agreement(terms={"board_size": 9})),
        )


def test_the_inbox_is_peeked_and_never_waited_on() -> None:
    """A path that is already failing must not also become a slow one."""
    seen: list[float] = []

    def receive(timeout):
        seen.append(timeout)
        return None

    with pytest.raises(ConnectionError):
        exchange_agreement(terms=TERMS, identity={}, declarations=dict(OURS),
                           send=refuses, receive=receive)

    assert seen == [0.0]
