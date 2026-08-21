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

#: How long to *listen* after our own call to a peer has failed, instead of
#: sleeping and dialling again.
#:
#: A peer that runs one process per window does not exist between windows, so
#: for most of a mini-game there is no door to dial and no amount of patience
#: invents one. What does exist is the moment their next window opens — and the
#: first thing it does is dial *us*. That knock is the only reliable signal that
#: a door is there at all, and it arrives on a connection they opened, which is
#: precisely the direction we have never had trouble with.
#:
#: So a failed call is followed by listening rather than by another call. It
#: costs the same wall clock as the sleep it replaces, and against anrbj666 on
#: 2026-08-19 our cop spent a whole mini-game dialling a thief process that had
#: not been spawned yet — 8-9 greetings a minute arriving here while every call
#: of ours timed out. The signal was in our inbox the entire time.
LISTEN_SECONDS = 10.0


def agreement_in_hand(
    receive: Any,
    declarations: dict[str, Any] | None,
    announce: Emit,
    error: Exception,
    wait: float = 0.0,
    hold: Any = None,
) -> dict[str, Any] | None:
    """Their agreement for *this* window, if it is already waiting for us.

    Input: the inbox reader, the declarations we are sending this window, the
        event sink, the error our own send raised, and optionally `hold`, a
        callable handed `(window, message)` for every agreement that names a
        *different* window than ours.
    Output: the peer's agreement message, or None when there is nothing usable
        — in which case the caller re-raises and the attempt is retried.
    Setup: none; `receive` is polled with a zero timeout, so this never adds a
        wait to a path that is already failing.

    `wait` is how long to listen. Zero is a peek, which is right when the peer
    has just answered us and is therefore demonstrably there. When our call
    failed outright, listening is strictly better than peeking-and-redialling:
    the peer may not have spawned yet, and their first act on spawning is to
    dial us.
    """
    peer = receive(wait)
    if peer is None:
        return None
    ours = _window(declarations or {})
    theirs = _window(peer)
    if ours and theirs and ours != theirs:
        # Not put back: a queue we can only pop from would hand us the same
        # stale message on every future peek. **Held, never merely dropped**:
        # the mismatch is the one signal that says which window the peer is
        # actually in, and discarding it is how the anrbj666 friendly of
        # 2026-08-21 died — our thief at window 5 dropped their window-3
        # negotiates on the floor, each side refused every offer of the
        # other, and two windows clocked out at step 0. The holder
        # (`sdk/handshake_setup` keys them by window) is what lets the series
        # rewind to the window the peer is demonstrably still holding, and it
        # seeds the rewound handshake with the very agreement that proved it.
        announce({
            "event": "handshake.window_mismatch", "ours": ours, "theirs": theirs,
            "held": hold is not None,
        })
        if hold is not None:
            hold(theirs, peer)
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


def window_of(message: dict[str, Any]) -> int:
    """The mini-game a negotiate names, 0 for none — `_window`, made public."""
    return _window(message)
