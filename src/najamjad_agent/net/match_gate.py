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
        self._lock = threading.Lock()
        self._emit = emit or (lambda _event: None)

    @property
    def open(self) -> bool:
        """True when a handshake is welcome."""
        with self._lock:
            return not self._in_play

    def begin_sub_game(self) -> None:
        """A mini-game is now in play; further handshakes are premature."""
        with self._lock:
            self._in_play = True

    def end_sub_game(self) -> None:
        """The mini-game resolved; the next handshake is expected.

        Idempotent on purpose. This is called from a `finally`, and a
        mini-game that raised must still reopen the gate — a crash that left
        it shut would make the agent permanently unchallengeable while
        appearing healthy, which is a worse failure than the one being fixed.
        """
        with self._lock:
            self._in_play = False

    def refuse(self) -> str | None:
        """The reason to reject a handshake, or None to let it through."""
        if self.open:
            return None
        self._emit({"event": "handshake.refused", "reason": BUSY_REASON})
        return BUSY_REASON
