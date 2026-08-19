"""When a window starts on their agreement, ours still has to reach them.

`inbound_first` lets a mini-game begin on the peer's negotiate after our own
send raised. That fixes our side and leaves theirs: the reference
implementation waits for our agreement and prints "Opponent never sent its
agreement" before a single move is played, so a window we can play is one they
would still abandon.

The address that finally works is the one their identity declares — the door
their *this*-role process answers on, which is exactly what we did not have
when the send failed. So the retry belongs after the retarget.

It does **not** belong in a function that cannot raise. This file said the
opposite until anrbj666 g6 on 2026-08-19 disproved it live: delivery failed
against a 502 door, we started the window on their agreement alone, they
re-sent their negotiate thirty times into a gate we had just shut, and the
watchdog scored the game TIMEOUT at `step=0`. An agreement is mutual or it is
nothing, and a window only one side holds is worse than a window neither does —
a handshake we retry costs seconds, this cost four minutes and a technical
result.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from najamjad_agent.sdk.handshake_setup import _deliver_late, _record_send

PAYLOAD = {"terms": {"board_size": 7}, "nonce": "n", "signature": "s"}


class _Transport:
    """A peer door that works, or does not, on demand."""

    def __init__(self, working: bool = True) -> None:
        self.working = working
        self.sent: list[dict[str, Any]] = []

    def send_negotiate(self, payload: dict[str, Any]) -> Any:
        if not self.working:
            raise ConnectionError("All connection attempts failed")
        self.sent.append(payload)
        return {"accepted": True}


def test_a_delivered_agreement_is_not_sent_twice() -> None:
    """The ordinary path must be untouched — one negotiate per window."""
    transport, sent = _Transport(), {}

    _record_send(transport, sent, PAYLOAD)
    _deliver_late(transport, sent, lambda _event: None)

    assert transport.sent == [PAYLOAD]
    assert sent["delivered"] is True


def test_an_undelivered_agreement_is_pushed_once_the_door_is_known() -> None:
    """The inbound-first case: the send raised, the window started anyway."""
    transport, sent, events = _Transport(working=False), {}, []

    with suppress(ConnectionError):
        _record_send(transport, sent, PAYLOAD)
    transport.working = True                      # the retarget found their door
    _deliver_late(transport, sent, events.append)

    assert transport.sent == [PAYLOAD]
    assert [event["event"] for event in events] == ["handshake.delivered_late"]


def test_a_reply_that_carried_ours_counts_as_delivery() -> None:
    """The elegant half: their call already took our agreement home.

    A peer running one process per window only exists while that window is
    open, so the moment it dials us is the only moment we know a door is there
    — and our reply rode back down that same connection. Dialling again would
    be asking a door that may not exist yet, which is exactly the flooding that
    cost three windows on 2026-08-19.
    """
    class _Boxes:
        agreement_sent = 0

    boxes, transport, sent, events = _Boxes(), _Transport(working=False), {}, []

    with suppress(ConnectionError):
        _record_send(transport, sent, PAYLOAD, boxes)
    boxes.agreement_sent += 1          # their negotiate arrived; we answered it

    _deliver_late(transport, sent, events.append, boxes)

    assert [e["event"] for e in events] == ["handshake.delivered_in_reply"]
    assert transport.sent == [], "must not dial a door that may not be there"


def test_a_second_failure_refuses_the_window_rather_than_starting_it_alone() -> None:
    """anrbj666 g6: the window we started alone cost four minutes and a TIMEOUT.

    Raising sends us back through `agree_on_terms`, which retries — and their
    next negotiate then meets an open gate instead of the "a mini-game is in
    progress" refusal that deadlocked both sides.
    """
    from najamjad_agent.negotiation.handshake import HandshakeError

    transport, sent, events = _Transport(working=False), {}, []

    with suppress(ConnectionError):
        _record_send(transport, sent, PAYLOAD)

    with pytest.raises(HandshakeError, match="only one side holds this window"):
        _deliver_late(transport, sent, events.append)

    assert [event["event"] for event in events] == ["handshake.delivery_failed"]
    assert "ConnectionError" in events[0]["error"]


def test_nothing_is_sent_when_the_handshake_never_got_that_far() -> None:
    """No payload means no exchange happened; there is nothing to re-offer."""
    transport, events = _Transport(), []

    _deliver_late(transport, {}, events.append)

    assert transport.sent == [] and events == []


def test_the_late_delivery_runs_after_the_retarget() -> None:
    """Ordering is the fix. Sending first would use the door that just failed."""
    source = Path("src/najamjad_agent/sdk/handshake_setup.py").read_text(encoding="utf-8")
    exchange = source.index("peer = exchange_agreement(")
    retarget = source.index("            retarget(\n                transport.client,")
    late = source.index("_deliver_late(transport, sent, bus.publish, inboxes)")

    assert exchange < retarget < late, "deliver to the corrected address, not the failed one"
