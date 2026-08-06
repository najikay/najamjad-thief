"""What the event log says about connection failures, per endpoint.

Built because an opponent asked us for evidence and does not accept that the
failures are theirs — which is a fair position for them to hold, and one we
could not answer, because our own conclusion had been published from a single
log line and was wrong.

So this computes rather than argues. The one thing we can state without
interpretation is the **control**: identical client code, identical process,
identical session lifecycle, connecting to several different endpoints in the
same period. The client is the constant and the endpoint is the variable, so a
failure rate that differs by two orders of magnitude between endpoints is a fact
about the endpoints, whatever the mechanism turns out to be.

It deliberately stops short of a verdict. `first_faults` reports the exception
that *opened* each cascade rather than the hundred identical wrappers that
followed it, because that is the only part of the record that names a mechanism,
and naming a mechanism is as far as this data goes.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Events that mean a connection attempt failed.
FAILURE_EVENTS = frozenset({"client.session_failed", "client.drop_failed", "client.reconnecting"})
#: Events that mean one was established.
SUCCESS_EVENTS = frozenset({"client.session_opened"})


@dataclass
class EndpointHealth:
    """Connection outcomes for one peer address."""

    url: str
    opened: int = 0
    failed: int = 0
    faults: Counter = field(default_factory=Counter)

    @property
    def attempts(self) -> int:
        """Every attempt we can attribute to this endpoint."""
        return self.opened + self.failed

    @property
    def failure_rate(self) -> float:
        """Share of attempts that failed, 0.0 when we never dialled it."""
        return self.failed / self.attempts if self.attempts else 0.0

    def as_dict(self) -> dict[str, Any]:
        """Report form."""
        return {
            "url": self.url,
            "opened": self.opened,
            "failed": self.failed,
            "failure_rate": round(self.failure_rate, 4),
            "faults": dict(self.faults.most_common()),
        }


def load_events(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL event log, skipping lines a crash left half-written."""
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def endpoint_health(events: list[dict[str, Any]]) -> list[EndpointHealth]:
    """Per-endpoint connection outcomes, worst first.

    Input: parsed events.
    Output: one `EndpointHealth` per URL, ordered by failure count.
    Setup: none — pure, so the opponent can re-run it on their copy of the log.
    """
    health: dict[str, EndpointHealth] = defaultdict(lambda: EndpointHealth(""))
    for event in events:
        url = event.get("url")
        if not isinstance(url, str) or not url:
            continue
        record = health[url]
        record.url = url
        name = event.get("event")
        if name in SUCCESS_EVENTS:
            record.opened += 1
        elif name in FAILURE_EVENTS:
            record.failed += 1
            record.faults[str(event.get("error") or "unnamed")] += 1
    return sorted(health.values(), key=lambda each: -each.failed)


def first_faults(events: list[dict[str, Any]]) -> Counter:
    """The exception that *opened* each failure cascade.

    The distinction is the whole point. A storm logs one real fault and then a
    hundred copies of the wrapper the retry loop produces, so counting every
    failure equally reports the retry policy rather than the fault. A cascade
    starts at the first failure after any success.
    """
    faults: Counter = Counter()
    in_storm = False
    for event in events:
        name = event.get("event")
        if name in SUCCESS_EVENTS:
            in_storm = False
        elif name in FAILURE_EVENTS:
            if not in_storm:
                detail = str(event.get("detail") or "")
                label = str(event.get("error") or "unnamed")
                faults[f"{label}: {detail[:60] or '<empty message>'}"] += 1
            in_storm = True
    return faults


def unnamed_share(events: list[dict[str, Any]]) -> tuple[int, int]:
    """How many failures carried no usable message — `(unnamed, total)`.

    The number that explains why this took so long to diagnose: an exception
    whose `str()` is empty logs its type and nothing else, and the type is the
    same for every connect-level fault fastmcp wraps.
    """
    total = unnamed = 0
    for event in events:
        if event.get("event") not in FAILURE_EVENTS:
            continue
        total += 1
        detail = str(event.get("detail") or "").strip()
        if not detail or detail.endswith(":"):
            unnamed += 1
    return unnamed, total
