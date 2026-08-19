"""When a window starts on their agreement, ours still has to reach them.

`inbound_first` lets a mini-game begin on the peer's negotiate after our own
send raised. That fixes our side and leaves theirs: the reference
implementation waits for our agreement and prints "Opponent never sent its
agreement" before a single move is played, so a window we can play is one they
would still abandon.

The address that finally works is the one their identity declares — the door
their *this*-role process answers on, which is exactly what we did not have
when the send failed. So the retry belongs after the retarget, and it belongs
in a function that cannot raise: we already hold an agreed window, and losing
it to a second connection failure would repeat the trade that cost g03.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

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


def test_a_second_failure_is_reported_and_never_raised() -> None:
    """We hold an agreed window; an exception here would throw it away."""
    transport, sent, events = _Transport(working=False), {}, []

    with suppress(ConnectionError):
        _record_send(transport, sent, PAYLOAD)
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
    late = source.index("_deliver_late(transport, sent, bus.publish)")

    assert exchange < retarget < late, "deliver to the corrected address, not the failed one"
