"""The event bus — one append-only stream feeding logs, UI and analysis.

Assignment 6 had a logging config that was never applied, so when the
negotiation agent misbehaved there was nothing to look at. Here every
subsystem publishes to a single sink, and that one stream is simultaneously:
the JSONL file, the dashboard's WebSocket feed, and the raw material for the
post-match notebook. One history, not three that disagree.

Subscriber failures are contained: a broken UI socket must never take down the
game loop that feeds it.
"""

import contextlib
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..protocol.canonical import canonical_json

Subscriber = Callable[[dict[str, Any]], None]
# What every subsystem accepts as its `emit` hook. The return type is `Any`
# rather than `None` on purpose: `EventBus.publish` returns the enriched event
# (useful to a caller that wants the stamped copy), and every emitter site
# ignores it. Declaring `None` made the bus's own method unassignable to the
# hook it exists to feed — a mismatch nothing caught until a `src` module
# finally wired the two together.
Emit = Callable[[dict[str, Any]], Any]
# Keys never written to the stream, whatever a caller passes (book rule 18).
REDACTED_KEYS = frozenset({"nonce", "nonces", "api_key", "token", "client_secret", "password"})
REDACTION = "<redacted>"


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets recursively before anything is persisted or broadcast."""
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in REDACTED_KEYS:
            clean[key] = REDACTION
        elif isinstance(value, dict):
            clean[key] = _scrub(value)
        else:
            clean[key] = value
    return clean


class EventBus:
    """Fan-out of correlated events to file and live subscribers.

    Input:  event dicts carrying at least an `event` name. Anything JSON-
            serialisable; callers add their own fields.
    Output: one JSON line per event appended to the log, and the same dict
            handed to every subscriber. This log is the **evidence** a replay
            and an audit are rebuilt from — the diagnostic channel is separate
            (`shared/logging_setup.py`, ADR-008).
    Setup:  `path` for the log file, created with its parents on first write so
            a fresh clone needs no preparation. The handle is held open: reopening
            per event cost 14 ms on a Windows-mounted filesystem, which is a
            missed deadline on a long turn.

    A subscriber must never block and never raise. Subscribers run on the
    publishing thread, so a slow one holds up a turn and a raising one would
    take observability's failure into the game loop.
    """

    def __init__(
        self,
        path: Path | None = None,
        correlation: dict[str, Any] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Create a bus; `correlation` is merged into every event (game_uid…)."""
        self._path = path
        self._correlation = dict(correlation or {})
        self._subscribers: list[Subscriber] = []
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._on_error = on_error
        self._handle: Any = None

    @property
    def history(self) -> list[dict[str, Any]]:
        """Every event published so far, in order."""
        with self._lock:
            return list(self._history)

    def correlate(self, **fields: Any) -> None:
        """Add or update the fields stamped onto subsequent events."""
        with self._lock:
            self._correlation.update(fields)

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        """Register a live consumer; returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(subscriber)

        def _unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return _unsubscribe

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        """Stamp, scrub, persist and broadcast one event.

        The timestamp is UTC and it is not optional. Ten thousand events were
        written without one, and the cost showed up the day an opponent offered
        their own server log to compare against ours: 713 requests on their side
        with timestamps, 1036 sends on ours with none, and no way to line up a
        single pair. The whole argument about whose fault the stalls were was
        unresolvable for want of a field that costs a microsecond.

        A caller may pass its own `ts` — a replayed or reconstructed event keeps
        the time it happened, not the time it was re-read.
        """
        stamped = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), **event}
        with self._lock:
            enriched = _scrub({**self._correlation, **stamped})
            self._history.append(enriched)
            subscribers = list(self._subscribers)
        self._append(enriched)
        for subscriber in subscribers:
            self._deliver(subscriber, enriched)
        return enriched

    def _append(self, event: dict[str, Any]) -> None:
        """Append one JSONL line; a full disk must not stop the game.

        The handle is opened once and kept. Re-opening per event costs 14 ms on
        a Windows mount against 0.02 ms on a Linux filesystem — and this project
        is developed on `/mnt/c`, where that turned the event log into the
        slowest thing in a match. Every line is still flushed immediately, so a
        crash loses nothing: the point of the log is to survive us.
        """
        if self._path is None:
            return
        try:
            handle = self._open()
            handle.write(canonical_json(event) + "\n")
            handle.flush()
        except OSError as error:
            self._report("file", error)

    def _open(self) -> Any:
        """The append handle, opened on first use."""
        if self._handle is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
            self._handle = self._path.open("a", encoding="utf-8")  # type: ignore[union-attr]
        return self._handle

    def close(self) -> None:
        """Release the log file; safe to call more than once."""
        handle, self._handle = self._handle, None
        if handle is not None:
            with contextlib.suppress(OSError):
                handle.close()

    def _deliver(self, subscriber: Subscriber, event: dict[str, Any]) -> None:
        """Deliver to one subscriber, isolating its failures from the game."""
        try:
            subscriber(event)
        except Exception as error:  # noqa: BLE001 - a bad UI socket must not stop play
            self._report("subscriber", error)

    def _report(self, source: str, error: Exception) -> None:
        """Surface a bus failure without recursing back into publish()."""
        if self._on_error is not None:
            self._on_error(source, error)
