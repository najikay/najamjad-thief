"""Watchdog — rescue state when the main loop stops breathing.

Book rule 7. A frozen agent is worse than a crashed one: the opponent waits out
their own deadline and both sides can end up with nothing. The watchdog notices
the silence, persists whatever we know (so the audit trail survives), and shuts
down in a controlled way instead of leaving a zombie holding a tunnel open.

Threshold comes from config (default 60 s, negotiable per Appendix F Table 19),
never a literal in the loop.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

from ..shared.events import Emit


class Watchdog:
    """Monitors heartbeats and escalates when the loop goes quiet."""

    def __init__(
        self,
        threshold_seconds: float,
        persist_state: Callable[[], Any],
        controlled_shutdown: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
        emit: Emit | None = None,
    ) -> None:
        """Wire the watchdog to its rescue callbacks."""
        if threshold_seconds <= 0:
            raise ValueError("watchdog threshold must be positive")
        self._threshold = threshold_seconds
        self._persist = persist_state
        self._shutdown = controlled_shutdown
        self._clock = clock
        self._emit = emit or (lambda _event: None)
        self._last_beat = clock()
        self._fired = False
        self._lock = threading.Lock()
        self._timer: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def threshold(self) -> float:
        """Configured freeze threshold in seconds."""
        return self._threshold

    @property
    def fired(self) -> bool:
        """True once the rescue path has run."""
        return self._fired

    def beat(self) -> None:
        """Called by the game loop each turn to prove it is alive."""
        with self._lock:
            self._last_beat = self._clock()

    def silence(self) -> float:
        """Seconds since the last heartbeat."""
        with self._lock:
            return self._clock() - self._last_beat

    def check(self) -> bool:
        """Escalate if the loop has been silent past the threshold.

        Returns True when the rescue path ran. Idempotent: a second call after
        firing does not persist or shut down twice.
        """
        if self._fired or self.silence() < self._threshold:
            return False
        self._fired = True
        self._emit({"event": "watchdog.fired", "silence": round(self.silence(), 3)})
        self._rescue()
        return True

    def _rescue(self) -> None:
        """Persist first, then shut down — order matters for the audit trail."""
        try:
            self._persist()
            self._emit({"event": "watchdog.state_persisted"})
        except Exception as error:  # noqa: BLE001 - must still attempt shutdown
            self._emit({"event": "watchdog.persist_failed", "error": type(error).__name__})
        try:
            self._shutdown()
            self._emit({"event": "watchdog.shutdown"})
        except Exception as error:  # noqa: BLE001 - nothing left to fall back to
            self._emit({"event": "watchdog.shutdown_failed", "error": type(error).__name__})

    def start(self, interval: float = 1.0) -> None:
        """Run periodic checks on a daemon thread."""
        if self._timer is not None:
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(interval):
                self.check()

        self._timer = threading.Thread(target=_loop, name="watchdog", daemon=True)
        self._timer.start()

    def stop(self) -> None:
        """Stop the monitoring thread (idempotent)."""
        self._stop.set()
        if self._timer is not None:
            self._timer.join(timeout=2.0)
            self._timer = None
