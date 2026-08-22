"""One match at a time — refusing a handshake that would restart a live game.

Our MCP endpoint is public (book rule 10) and `negotiate` was ungated: any
caller could hand us a fresh terms proposal *in the middle of a mini-game* and
we would validate it, enqueue it, and answer `accepted`. `session_guard` binds
identity for turns precisely so a stranger cannot inject a move into a live
match — but the handshake that establishes who the opponent *is* had no such
protection, which left the front door open behind the locked one.

This is not hypothetical. Against ahk-yosi we logged **58 inbound negotiates**
across a six-game series: their peer was hosted and retrying our endpoint on a
loop while we dialled theirs, so two games ran at once over one inbox and one
game state. Every turn wait was poisoned by the other game's traffic and all
five completed mini-games scored 0-0 technical. Neither side had done anything
the book forbids. Our server should have said no.

**Refusal must be retriable, not fatal.** Opponents re-handshake before every
mini-game, and a legitimate one whose clock runs slightly ahead of ours will
propose sub-game N+1 while we are still finishing N. Answering "malformed" or
dropping the connection would turn a timing skew into a forfeit. We answer
"busy, ask again" — their retry loop is then the mechanism that *resynchronises*
us, because the next attempt lands once we reach the boundary.

The gate is open by default. An agent that is merely listening — nobody has
started a match — must still accept the handshake that begins one, otherwise
the peer who dials second could never open a series at all.
"""

from __future__ import annotations

import threading
from typing import Any

from ..shared.events import Emit

BUSY_REASON = "a mini-game is in progress; re-send this handshake at the boundary"


class MatchGate:
    """Whether an inbound handshake may be acted on right now.

    Open between mini-games and before the series starts; closed from the
    moment a mini-game begins until it resolves.
    """

    def __init__(self, emit: Emit | None = None) -> None:
        """Start open — a listening agent must be able to be challenged."""
        self._in_play = False
        #: Which window is in play, so a peer re-offering *that* window can be
        #: told apart from one running ahead of us.
        self._sub_game = 0
        self._lock = threading.Lock()
        self._emit = emit or (lambda _event: None)

    @property
    def open(self) -> bool:
        """True when a handshake is welcome."""
        with self._lock:
            return not self._in_play

    def begin_sub_game(self, sub_game: int = 0) -> None:
        """A mini-game is now in play; further handshakes are premature."""
        with self._lock:
            self._in_play = True
            self._sub_game = int(sub_game)

    def end_sub_game(self) -> None:
        """The mini-game resolved; the next handshake is expected.

        Idempotent on purpose. This is called from a `finally`, and a
        mini-game that raised must still reopen the gate — a crash that left
        it shut would make the agent permanently unchallengeable while
        appearing healthy, which is a worse failure than the one being fixed.
        """
        with self._lock:
            self._in_play = False

    def refuse(self, message: Any = None, turns_seen: bool = False) -> str | None:
        """The reason to reject a handshake, or None to let it through.

        **A re-offer of the window we are already in is not premature.** We
        start a window the moment *our* side agrees, which can be seconds before
        the peer considers it agreed — and everything they send to close that
        gap is a negotiate for the very window we are sitting in. Refusing those
        is how both sides wait forever: anrbj666's thief re-offered g04
        thirty-one times on 2026-08-21 while our police, having already started
        g04, answered "busy" to every one and then timed out at step 0 waiting
        for an opener they had no agreed window to send.

        So a handshake naming the window in play is accepted while no turn has
        been exchanged yet. It is idempotent by construction — the terms are
        identical and our server answers with our own agreement attached, so the
        peer gets what it was missing and the game we are already in continues
        untouched. Once turns are flowing, `turns_seen` closes it again, because
        then a fresh negotiate really would be restarting a live game.
        """
        if self.open:
            return None
        if not turns_seen and _names_our_window(message, self._sub_game):
            self._emit({"event": "handshake.reoffer_accepted", "sub_game": self._sub_game})
            return None
        self._emit({"event": "handshake.refused", "reason": BUSY_REASON})
        return BUSY_REASON


def _names_our_window(message: Any, sub_game: int) -> bool:
    """Whether this handshake is re-offering the window we are already in."""
    if not sub_game or message is None:
        return False
    declared = getattr(message, "sub_game_number", None)
    if declared is None:
        declared = (getattr(message, "extras", None) or {}).get("sub_game_number")
    if declared is None:
        return False
    try:
        return int(declared) == int(sub_game)
    except (TypeError, ValueError):
        return False
