"""Starting the window they opened, when our own knock never landed.

The exchange is symmetric by design — both peers send unconditionally and then
wait — but `exchange_agreement` only ever reached its `receive` after its `send`
returned. So a peer whose agreement was already sitting in our inbox, accepted
and answered `accepted: true` by our own server, could not start anything: our
outbound negotiate raised first, the whole attempt was scored a failure, and the
inbox was never looked at.

That is accept-without-start, and it is the first domino of the three that cost
us g03 against anrbj666. It bites hardest against a peer running cop and thief
as two processes on two doors, because the address we hold at the start of a
window is the one their *previous* role answered on: our send goes to a door
that is not in this game and fails, while their negotiate — sent to the door we
actually serve — arrives fine. Both peers healthy, both dialling correctly by
their own lights, and only one of them able to begin.

Their message is the thing that establishes agreement; ours is an announcement.
So a failed announcement is no longer a failed window when the agreement is
already here. We adopt it, verify it as strictly as ever, and deliver ours late
to the address their identity declares — which is the door that was missing in
the first place.

**The window number still binds.** Adopting an agreement that names a different
mini-game than the one we are offering is precisely how two honest reports come
to describe one game under two `sub_game_number`s, which rules 33-35 void for
both teams. A mismatch is therefore refused and recorded, never used; a peer
that declares no number at all is played normally, because omission has never
been a refusal on either side.
"""

from __future__ import annotations

from typing import Any

from ..shared.events import Emit


def agreement_in_hand(
    receive: Any,
    declarations: dict[str, Any] | None,
    announce: Emit,
    error: Exception,
) -> dict[str, Any] | None:
    """Their agreement for *this* window, if it is already waiting for us.

    Input: the inbox reader, the declarations we are sending this window, the
        event sink, and the error our own send raised.
    Output: the peer's agreement message, or None when there is nothing usable
        — in which case the caller re-raises and the attempt is retried.
    Setup: none; `receive` is polled with a zero timeout, so this never adds a
        wait to a path that is already failing.

    Not waiting is deliberate. The caller retries on a cadence of its own and
    each retry peeks again, so a message that arrives a few seconds from now is
    picked up by the next attempt rather than by a blocking read here — and a
    peer that is simply absent costs us nothing at all.
    """
    peer = receive(0.0)
    if peer is None:
        return None
    ours = _window(declarations or {})
    theirs = _window(peer)
    if ours and theirs and ours != theirs:
        # Dropped rather than put back: a queue we can only pop from would
        # otherwise hand us the same stale message on every future peek. Both
        # sides re-send per window, and that retry is what resynchronises us.
        announce({
            "event": "handshake.window_mismatch", "ours": ours, "theirs": theirs,
        })
        return None
    announce({
        "event": "handshake.inbound_first",
        "sub_game": theirs or ours,
        "error": f"{type(error).__name__}: {error}",
    })
    return peer


def _window(message: dict[str, Any]) -> int:
    """The mini-game a negotiate names, or 0 when it names none.

    Zero means "not declared" and never matches, so an undeclared window is
    played rather than refused.
    """
    try:
        return int(message.get("sub_game_number", 0) or 0)
    except (TypeError, ValueError):
        return 0
