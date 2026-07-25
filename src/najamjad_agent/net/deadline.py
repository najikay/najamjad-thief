"""Deadline tracking — a missed deadline is a failure, never patience.

Book rule 6: waiting forever for a peer that will never answer is how a match
dies with no result for either side. Every wait here is bounded, and when the
budget is exhausted we produce a **sealed evidence record** rather than simply
declaring ourselves the winner: the opponent (and the lecturer) can verify what
we waited for and for how long.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..domain.crypto import SealedRecord, seal


@dataclass
class Deadline:
    """One bounded wait with its expiry."""

    label: str
    started_at: float
    expires_at: float

    def remaining(self, now: float) -> float:
        """Seconds left before this deadline expires (never negative)."""
        return max(0.0, self.expires_at - now)

    def expired(self, now: float) -> bool:
        """True once the budget is spent."""
        return now >= self.expires_at


@dataclass
class DeadlineTracker:
    """Issues deadlines, records timeouts, and seals timeout evidence."""

    response_timeout: float = 30.0
    max_retries: int = 3
    clock: Callable[[], float] = time.monotonic
    emit: Callable[[dict], None] | None = None
    timeouts: list[dict[str, Any]] = field(default_factory=list)

    def start(self, label: str, timeout: float | None = None) -> Deadline:
        """Open a bounded wait for `label`."""
        now = self.clock()
        budget = self.response_timeout if timeout is None else timeout
        deadline = Deadline(label=label, started_at=now, expires_at=now + budget)
        self._event("deadline.started", label=label, budget=budget)
        return deadline

    def await_value(
        self,
        label: str,
        poll: Callable[[float], Any | None],
        timeout: float | None = None,
    ) -> Any | None:
        """Poll for a value within the deadline, retrying up to the budget.

        Returns None once the retry budget is exhausted — the caller then
        resolves the game cleanly instead of blocking forever.
        """
        for attempt in range(1, self.max_retries + 1):
            deadline = self.start(f"{label}#{attempt}", timeout)
            value = poll(deadline.remaining(self.clock()))
            if value is not None:
                self._event("deadline.met", label=label, attempt=attempt)
                return value
            self._event("deadline.expired", label=label, attempt=attempt)
        self.record_timeout(label, timeout if timeout is not None else self.response_timeout)
        return None

    def record_timeout(self, label: str, budget: float) -> dict[str, Any]:
        """Record a timeout occurrence for the log and the evidence record."""
        entry = {
            "label": label,
            "waited_seconds": round(budget * self.max_retries, 3),
            "attempts": self.max_retries,
            "at": self.clock(),
        }
        self.timeouts.append(entry)
        self._event("deadline.timeout", **entry)
        return entry

    def evidence(self, step: int, role: str, sub_game: int) -> SealedRecord:
        """Seal what we waited for, so a timeout claim is verifiable.

        The reference implementation lets a peer simply declare a timeout win;
        a sealed record turns that assertion into something the opponent can
        check against their own log during the audit.
        """
        payload = {
            "step": step,
            "type": "timeout_evidence",
            "role": role,
            "sub_game": sub_game,
            "timeouts": self.timeouts,
            "response_timeout": self.response_timeout,
            "max_retries": self.max_retries,
        }
        return seal(payload)

    def _event(self, name: str, **fields: Any) -> None:
        if self.emit is not None:
            self.emit({"event": name, **fields})
