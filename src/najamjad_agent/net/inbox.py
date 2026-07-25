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
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..protocol.ingress import ParseResult, parse_message
from ..protocol.schemas_wire import (
    AuditPayload,
    ControlMessage,
    NegotiateMessage,
    TurnMessage,
)

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
        emit: Callable[[dict], None] | None = None,
        maxsize: int = 1000,
    ) -> None:
        """Create the queues; `emit` receives every accept/reject event."""
        self._queues = {kind: queue.Queue(maxsize=maxsize) for kind in KINDS}
        self._emit = emit or (lambda _event: None)
        self._last_step = -1
        self._lock = threading.Lock()

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
        """Reject replayed or stale turns before they reach the game state."""
        step = getattr(message, "step", None)
        if step is None:
            return None
        with self._lock:
            if step <= self._last_step:
                return (
                    f"step {step} is stale or replayed (last accepted was {self._last_step})"
                )
            self._last_step = step
        return None

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
