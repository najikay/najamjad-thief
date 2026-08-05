"""The API gatekeeper — every external call passes through here.

Mandated by the guidelines (§5) and, for Gmail, by the book (rules 28-29): a
token-bucket limiter plus queueing, because a burst of retries against Google
can get the sending account suspended — and the account is how we score points.

Design choices that matter under contention:

* **Overflow queues, it does not reject.** Callers get backpressure (a wait),
  not a dropped move.
* **Retries are bounded and logged.** A silent infinite retry is indistinguishable
  from a hang, which is exactly how a match dies.
* **Every call is logged** through the event sink, so the dashboard can show
  queue depth and the post-match analysis can explain a slow turn.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from ..shared.events import Emit
from .error_detail import describe
from .rate_limits import RateLimitConfig

ResultT = TypeVar("ResultT")


class QueueFullError(Exception):
    """Raised when the queue is at its configured depth (backpressure signal)."""


@dataclass
class QueueStatus:
    """Snapshot of gatekeeper load for the dashboard.

    Input:  none — built by the gatekeeper from its own counters.
    Output: `service`, plus how many calls are waiting and in flight. Read-only
            and point-in-time; it describes the queue, it does not control it.
    Setup:  none. A value object deliberately, so a panel cannot hold a
            reference that mutates while it renders.
    """

    service: str
    waiting: int
    in_flight: int
    tokens: float
    calls_made: int


@dataclass
class ApiGatekeeper:
    """Token-bucket limiter, FIFO queue and bounded retries for one service.

    Input:  any callable plus its arguments, executed through `execute()`.
    Output: the callable's return value, or `RuntimeError` after `max_retries`
            transient failures. Every attempt, wait and failure is evented, so
            queue depth and back-off are visible rather than inferred.
    Setup:  `service` (the name used in `config/rate_limits.json`) and a
            `RateLimitConfig`. One instance per service — Anthropic's quota and
            Gmail's are unrelated, and sharing a bucket would make one outage
            throttle the other.

    Applies to **outbound third-party calls**. Our own protocol traffic to the
    opponent is not metered by anyone, and throttling it only risks missing
    their 30-second deadline — which is how a limiter forfeits a game.
    """

    service: str
    config: RateLimitConfig
    emit: Emit | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _tokens: float = field(init=False, default=0.0)
    _updated: float = field(init=False, default=0.0)
    _waiting: int = field(init=False, default=0)
    _in_flight: int = field(init=False, default=0)
    _calls: int = field(init=False, default=0)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        """Start with a full bucket so the first burst is not penalised."""
        self._tokens = float(self.config.requests_per_minute)
        self._updated = self.clock()

    def status(self) -> QueueStatus:
        """Current load, safe to poll from the UI thread."""
        with self._lock:
            return QueueStatus(self.service, self._waiting, self._in_flight, self._tokens, self._calls)

    def _event(self, name: str, **fields: Any) -> None:
        if self.emit is not None:
            self.emit({"event": name, "service": self.service, **fields})

    def _refill(self) -> None:
        """Add tokens for elapsed time, capped at one minute's worth."""
        now = self.clock()
        elapsed = max(0.0, now - self._updated)
        rate = self.config.requests_per_minute / 60.0
        self._tokens = min(float(self.config.requests_per_minute), self._tokens + elapsed * rate)
        self._updated = now

    def _take_token(self) -> bool:
        """Consume one token if available."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0 and self._in_flight < self.config.concurrent_max:
                self._tokens -= 1.0
                self._in_flight += 1
                return True
            return False

    def _release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._calls += 1

    def _admit(self) -> None:
        """Wait for capacity, honouring the configured queue depth."""
        with self._lock:
            if self._waiting >= self.config.queue_depth:
                self._event("gatekeeper.backpressure", waiting=self._waiting)
                raise QueueFullError(
                    f"{self.service}: queue depth {self.config.queue_depth} reached"
                )
            self._waiting += 1
        try:
            while not self._take_token():
                self._event("gatekeeper.queued", waiting=self._waiting)
                self.sleep(60.0 / max(1, self.config.requests_per_minute))
        finally:
            with self._lock:
                self._waiting = max(0, self._waiting - 1)

    def _out_of_time(self, started: float, attempt: int) -> bool:
        """Whether another attempt would finish after anyone still cares.

        The retry budget was never the number of retries — it was always the
        clock, and we were counting the wrong one. `mcp_peer` allows ten
        attempts five seconds apart and the config called that "about 45 s of
        persistence", but each attempt is itself bounded by a 30 s call timeout
        and `PeerSession` reconnects once inside that, so one message could
        occupy **645 s**. The agreed `watchdog_timeout_sec` is 60. Everything
        past roughly 45 s is time spent after the opponent has already scored
        the turn against us, and it is not free: our own turn loop is blocked
        in that send, so the minutes come straight out of the next mini-game.

        Deliberately measured *including* the pending back-off, because the
        question is whether the next attempt lands inside the budget, not
        whether this instant does.

        **What this does not promise.** It governs whether a *new* attempt may
        start and cannot reach into one already in flight, so the true ceiling
        is the deadline plus one response timeout — and Table 19 fixes that
        timeout at 30 s, so for two or more attempts no legal configuration
        stays under a 60 s watchdog. 645 s becomes 65 s, not 45. The residue is
        why `MatchRunner`'s freeze threshold is a multiple of the agreed
        watchdog and not equal to it.
        """
        deadline = self.config.deadline_seconds
        if not deadline:
            return False
        spent = self.clock() - started
        if spent + self.config.retry_after_seconds < deadline:
            return False
        self._event(
            "gatekeeper.deadline",
            attempt=attempt,
            spent=round(spent, 3),
            deadline=deadline,
        )
        return True

    def execute(self, api_call: Callable[..., ResultT], *args: Any, **kwargs: Any) -> ResultT:
        """Run `api_call` under the limiter, retrying transient failures."""
        last_error: Exception | None = None
        started = self.clock()
        attempt = 0
        for attempt in range(1, self.config.max_retries + 1):
            self._admit()
            try:
                result = api_call(*args, **kwargs)
            except Exception as error:  # noqa: BLE001 - re-raised below after logging
                last_error = error
                self._event(
                    "gatekeeper.retry",
                    attempt=attempt,
                    # The type alone is not enough to act on, and finding that
                    # out cost a day. Three police mini-games died to ten
                    # `RuntimeError`s each, and `RuntimeError` is what fastmcp
                    # raises for *every* connect-level fault — its own message
                    # is the only thing that separates "nothing is listening"
                    # from a protocol error.
                    #
                    # Then the message turned out to be empty 152 times out of
                    # 154, so the type-plus-message pair named nothing either.
                    # `describe` adds the cause chain underneath it, which is
                    # where the answer actually was. Truncated inside, because a
                    # vendor can return a whole HTML page as its `str()`.
                    **describe(error),
                    backoff=self.config.retry_after_seconds,
                )
                if attempt < self.config.max_retries:
                    if self._out_of_time(started, attempt):
                        break
                    self.sleep(self.config.retry_after_seconds)
            else:
                self._event("gatekeeper.call", attempt=attempt)
                return result
            finally:
                self._release()
        self._event(
            "gatekeeper.failed",
            # What we actually ran, not the ceiling. The deadline can stop us
            # early, and `analysis/connection_forensics.py` reads this field —
            # reporting ten attempts when nine ran turns the forensics into
            # fiction in exactly the situation they exist to explain.
            attempts=attempt,
            spent=round(self.clock() - started, 3),
            **(describe(last_error) if last_error else {"error": "", "detail": "", "cause": ""}),
        )
        raise RuntimeError(f"{self.service}: failed after {attempt} attempts") from last_error
