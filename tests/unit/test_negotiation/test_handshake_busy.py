"""A peer whose gate is shut is not a peer who is gone.

Amjad, 2026-08-06: he started a few seconds before us, locked, and opened
sub-game 1. Our handshake then arrived at a closed gate and his server answered
— immediately, over a healthy connection — "a mini-game is in progress; re-send
this handshake at the boundary".

We discarded that answer and blocked on `receive(timeout)` as though nobody had
replied. Three attempts at 60 s each: 180 s of silence while he played sub-game
1 and timed out waiting for turns we could not send. The retry loop is meant to
be the thing that resynchronises two drifted clocks, and it was keyed on a
timeout rather than on the refusal that had already arrived.

Both sides run this code, so the fix is symmetric.
"""

import pytest

from najamjad_agent.negotiation.handshake import (
    HandshakeBusyError,
    exchange_agreement,
    refused_as_busy,
)
from najamjad_agent.net.match_gate import BUSY_REASON

TERMS = {"board_size": 7, "num_games": 6}
BUSY = {"accepted": False, "kind": "negotiate", "errors": [BUSY_REASON]}


def test_a_busy_refusal_is_recognised_in_the_reply_body() -> None:
    """`mcp_server._handle` never raises at a caller, so this is the signal."""
    assert refused_as_busy(BUSY)


def test_other_answers_are_not_mistaken_for_busy() -> None:
    """An accepted handshake, a schema rejection, and junk are all different."""
    assert not refused_as_busy({"accepted": True, "kind": "negotiate"})
    assert not refused_as_busy({"accepted": False, "errors": ["terms mismatch"]})
    assert not refused_as_busy(None)
    assert not refused_as_busy("busy")


def test_we_do_not_wait_out_a_peer_who_already_answered() -> None:
    """The defect: the refusal arrives at once, then we waited the full timeout.

    The inbox is now *peeked* on this path — a shut gate can mean they are
    already playing the very window we are asking for, off a negotiate of
    theirs we accepted. That peek is free and must stay free: any timeout above
    zero here is the original bug returning.
    """
    seen: list[float] = []

    def receive(timeout):
        seen.append(timeout)
        return None

    with pytest.raises(HandshakeBusyError, match="mini-game is in progress"):
        exchange_agreement(
            terms=TERMS, identity={}, send=lambda _payload: BUSY, receive=receive
        )

    assert seen == [0.0], "a refusal already told us why; there is nothing to wait for"


def test_the_refusal_is_announced_with_their_own_words() -> None:
    """An operator reading the log needs to see it was a gate, not an outage."""
    events: list[dict] = []

    with pytest.raises(HandshakeBusyError):
        exchange_agreement(
            terms=TERMS,
            identity={},
            send=lambda _payload: BUSY,
            receive=lambda _timeout: None,
            emit=events.append,
        )

    busy = [event for event in events if event["event"] == "handshake.busy"]
    assert busy and BUSY_REASON in busy[0]["detail"]


def test_a_normal_handshake_is_untouched() -> None:
    """A server that returns nothing useful must still work exactly as before.

    The reference answers `{"accepted": True}`; older fakes answer `None`.
    Neither is a refusal, and both must fall through to the receive.
    """
    from najamjad_agent.negotiation.contract import Contract

    peer = Contract(dict(TERMS)).signed()

    for answer in (None, {"accepted": True, "kind": "negotiate"}):
        got = exchange_agreement(
            terms=TERMS, identity={}, send=lambda _p, a=answer: a, receive=lambda _t: peer
        )
        assert got["terms"] == TERMS
