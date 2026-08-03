"""Thread-safe inboxes between the MCP server thread and the game loop.

The FastMCP tools run on a server thread and must return immediately; the game
loop consumes at its own pace. Queues decouple them, and validation happens at
intake so a malformed message is rejected while the sender is still listening
— it gets a structured error instead of a silent drop.

`drain` exists for the gap between mini-games: leftovers from a finished game
must never be consumed as the first turn of the next one.
"""

import queue
import threading
from typing import Any

from pydantic import BaseModel

from ..protocol.ingress import ParseResult, parse_message
from ..protocol.schemas_wire import (
    AuditPayload,
    ControlMessage,
    NegotiateMessage,
    TurnMessage,
)
from ..shared.events import Emit
from .match_gate import MatchGate
from .session_guard import DEFAULT_MAX_PER_MINUTE, SessionGuard
from .sub_game_boundary import FIRST_STEP, clear_finished_game

# One queue per message kind: a flood of control messages must not delay a turn.
KINDS: dict[str, type[BaseModel]] = {
    "negotiate": NegotiateMessage,
    "turn": TurnMessage,
    "audit": AuditPayload,
    "control": ControlMessage,
}


class Inboxes:
    """Validated, per-kind message queues with a sequence guard on turns."""

    def __init__(
        self,
        emit: Emit | None = None,
        maxsize: int = 1000,
        guard: SessionGuard | None = None,
        max_per_minute: int = DEFAULT_MAX_PER_MINUTE,
        gate: MatchGate | None = None,
    ) -> None:
        """Create the queues; `emit` receives every accept/reject event."""
        self._queues = {kind: queue.Queue(maxsize=maxsize) for kind in KINDS}
        self._emit = emit or (lambda _event: None)
        self._last_step = -1
        self._lock = threading.Lock()
        self.guard = guard or SessionGuard(emit=emit, max_per_minute=max_per_minute)
        self.gate = gate or MatchGate(emit=emit)

    def accept(self, kind: str, raw: Any) -> ParseResult:
        """Validate and enqueue one inbound message, returning the verdict."""
        if kind not in KINDS:
            return ParseResult(errors=[f"<root>: unknown message kind {kind!r}"])
        result = parse_message(KINDS[kind], raw)
        if not result.ok:
            self._emit({"event": "inbox.rejected", "kind": kind, "errors": result.errors})
            return result
        if result.unknown_fields:
            # Tolerated by design (ADR-006) but always visible, so an opponent's
            # protocol extension is discovered rather than silently ignored.
            self._emit(
                {"event": "inbox.unknown_fields", "kind": kind, "fields": result.unknown_fields}
            )
        # Identity and rate before sequence: a stranger's turn must not even
        # be allowed to advance our step counter.
        refusal = self.guard.check(result.model)
        if refusal:
            self._emit({"event": "inbox.unauthorised", "kind": kind, "reason": refusal})
            return ParseResult(errors=[refusal])
        if kind == "negotiate":
            # A handshake mid-mini-game would restart the game we are playing.
            # Retriable by design: the peer asks again at the boundary, and
            # that retry is what resynchronises two clocks that drifted.
            busy = self.gate.refuse()
            if busy:
                return ParseResult(errors=[busy])
        if kind == "turn":
            problem = self._check_sequence(result.model)
            if problem:
                self._emit({"event": "inbox.out_of_order", "kind": kind, "reason": problem})
                return ParseResult(errors=[problem])
        try:
            self._queues[kind].put_nowait(result.model)
        except queue.Full:
            self._emit({"event": "inbox.full", "kind": kind})
            return ParseResult(errors=[f"<root>: {kind} queue is full"])
        self._emit({"event": "inbox.accepted", "kind": kind})
        return result

    def _check_sequence(self, message: Any) -> str | None:
        """Reject replayed or stale turns before they reach the game state.

        Step 1 is the exception, and it has to be: every mini-game restarts
        numbering at 1, so after a game ending at step 11 the next game's
        opening turn is a legitimate step 1 that this guard would otherwise
        read as a replay.

        The transport also clears the mark between mini-games, but that alone
        is a race — the peer who finishes first sends its next game's opening
        turn before the slower peer has reset, and the turn is dropped by a
        guard that is merely a moment out of date. Whoever wins that race
        should not decide whether the series continues.

        Nothing on the wire distinguishes the two cases: the reference's
        `TurnMessage` has no sub-game field, and it builds messages with
        `cls(**data)`, so adding one would make every turn we send raise a
        `TypeError` in their process. Step 1 is the only signal available, and
        treating it as "a new mini-game started" costs only the ability to
        detect a replayed *first* turn — whose payload is sealed and whose
        duplicate the game's own state machine refuses anyway.
        """
        step = getattr(message, "step", None)
        if step is None:
            return None
        if getattr(message, "claim_response", None) is not None:
            # The answer to a capture claim is allowed to arrive at the step it
            # answers. The reference sends its concession as a *final* message
            # without advancing its counter, so a strict monotonic guard rejects
            # the one message we are waiting for and the game stalls at the
            # moment we captured — which is exactly what it did.
            #
            # This does not reopen replay: an answer is idempotent, the game
            # ends on the first one, and the payload behind it is sealed like
            # every other.
            return None
        with self._lock:
            if step == FIRST_STEP and self._last_step > FIRST_STEP:
                # A game that has already run past its opening turn cannot
                # receive another one; this is the next mini-game beginning.
                # Requiring `> FIRST_STEP` keeps a replayed *first* turn
                # rejected, which a bare "step 1 always resets" would not.
                self._last_step = step
                return None
            if step <= self._last_step:
                return (
                    f"step {step} is stale or replayed (last accepted was {self._last_step})"
                )
            self._last_step = step
        return None

    def begin_sub_game(self) -> dict[str, int]:
        """Prepare for the next mini-game without discarding its opening turn.

        The rule for what survives the boundary lives in `sub_game_boundary`.
        """
        dropped, held_opening = clear_finished_game(self._queues)
        # From here until the mini-game resolves, an inbound handshake is
        # premature and gets a retriable refusal rather than restarting us.
        self.gate.begin_sub_game()
        with self._lock:
            # If the opening turn is already in hand, the mark moves with it —
            # otherwise accepting it off the queue would read as a replay.
            self._last_step = FIRST_STEP if held_opening else -1
        if dropped:
            self._emit({"event": "inbox.sub_game_started", "dropped": dropped})
        return dropped

    def poll(self, kind: str, timeout: float) -> Any | None:
        """Wait up to `timeout` for the next message of `kind`."""
        try:
            return self._queues[kind].get(timeout=timeout)
        except queue.Empty:
            return None

    def pending(self, kind: str) -> int:
        """How many messages of `kind` are waiting (dashboard metric)."""
        return self._queues[kind].qsize()

    def drain(self) -> dict[str, int]:
        """Empty every queue and reset the sequence guard between mini-games."""
        dropped: dict[str, int] = {}
        for kind, box in self._queues.items():
            count = 0
            while True:
                try:
                    box.get_nowait()
                except queue.Empty:
                    break
                count += 1
            if count:
                dropped[kind] = count
        with self._lock:
            self._last_step = -1
        if dropped:
            self._emit({"event": "inbox.drained", "dropped": dropped})
        return dropped
