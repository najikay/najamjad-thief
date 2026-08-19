"""Thread-safe inboxes between the MCP server thread and the game loop.

The FastMCP tools run on a server thread and must return immediately; the game
loop consumes at its own pace. Queues decouple them, and validation happens at
intake so a malformed message is rejected while the sender is still listening
— it gets a structured error instead of a silent drop.

`drain` exists for the gap between mini-games: leftovers from a finished game
must never be consumed as the first turn of the next one.
"""

import queue
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
from .sub_game_boundary import clear_finished_game
from .turn_sequence import TurnSequence

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
        self.sequence = TurnSequence()
        self.guard = guard or SessionGuard(emit=emit, max_per_minute=max_per_minute)
        self.gate = gate or MatchGate(emit=emit)
        #: Our signed agreement for the window being negotiated, so the server
        #: can hand it back in the reply to *their* negotiate. A handshake needs
        #: both agreements to cross, and it has cost us three windows that those
        #: are two separate outbound calls: when ours fails and theirs works, the
        #: link is fine in the direction that matters and we still cannot finish.
        #: Answering in-band completes the exchange over the connection the peer
        #: already opened. Set by the handshake, read by the server thread.
        self.our_agreement: dict[str, Any] | None = None

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
            problem = self._sequence_problem(result.model)
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

    def _sequence_problem(self, message: Any) -> str | None:
        """Ask `TurnSequence` whether this turn belongs here, at this step."""
        step = getattr(message, "step", None)
        if step is None:
            return None
        answers = getattr(message, "claim_response", None) is not None
        return self.sequence.check(step, answers)

    def begin_sub_game(self) -> dict[str, int]:
        """Prepare for the next mini-game without discarding its opening turn.

        The rule for what survives the boundary lives in `sub_game_boundary`.
        """
        dropped, held_opening = clear_finished_game(self._queues)
        # From here until the mini-game resolves, an inbound handshake is
        # premature and gets a retriable refusal rather than restarting us.
        self.gate.begin_sub_game()
        self.sequence.begin_sub_game(held_opening)
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
        self.sequence.drain()
        if dropped:
            self._emit({"event": "inbox.drained", "dropped": dropped})
        return dropped
