"""Is anyone actually reachable? — the pre-match question, answered at a glance.

Three URLs decide whether a match can happen: the local server, the tunnel that
publishes it, and the opponent's endpoint. Before this existed, checking them
meant three `curl`s and knowing which three, which is a bad thing to be doing at
20:00 with an opponent waiting.

**What a green light means, precisely:** for an `http(s)` endpoint, an MCP
server answered below the 5xx range — it is running and talking, though not
necessarily agreeable to our terms; that is what the handshake is for. For a
bare `host:port`, something accepted a TCP connection.

It used to mean TCP in both cases, and that made the panel lie in the one
configuration that matters. A tunnel edge accepts TCP whether or not the agent
behind it is alive, so the panel reported "Everything configured is answering"
about an opponent who was not there — while the match wait, probing the same
address over HTTP, correctly recorded `opponent.absent`. Two probes disagreeing
about the same host is one probe too many: both now use `is_ready`.

The distinction that earns its keep is **unreachable versus unconfigured**. An
empty `opponent_url` is not a failure, it is a match not yet scheduled, and
painting it red teaches the operator to ignore red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .opponent_wait import endpoint_of, is_ready

UNCONFIGURED = "not configured"
UNPARSEABLE = "not a usable URL"
LISTENING = "answering"
SILENT = "not answering"


@dataclass(frozen=True)
class Probe:
    """One endpoint and what we could establish about it."""

    name: str
    url: str
    reachable: bool | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        """The shape the dashboard renders."""
        return {
            "name": self.name,
            "url": self.url,
            "reachable": self.reachable,
            "detail": self.detail,
        }


def check(name: str, url: str, timeout: float = 1.0) -> Probe:
    """Probe one endpoint. `reachable is None` means we did not ask."""
    if not url:
        return Probe(name, "", None, UNCONFIGURED)
    endpoint = endpoint_of(url)
    if endpoint is None:
        return Probe(name, url, False, UNPARSEABLE)
    host, port = endpoint
    if is_ready(url, host, port, timeout=timeout):
        return Probe(name, url, True, LISTENING)
    return Probe(name, url, False, SILENT)


def survey(endpoints: dict[str, str], timeout: float = 1.0) -> list[dict[str, Any]]:
    """Probe every named endpoint, in the order given.

    Sequential on purpose: three probes at a 1 s timeout is at worst three
    seconds, and a thread pool here would be concurrency for its own sake.
    """
    return [check(name, url, timeout=timeout).as_dict() for name, url in endpoints.items()]


def blocking_issues(probes: list[dict[str, Any]]) -> list[str]:
    """The names that would stop a match — configured but not answering.

    Unconfigured endpoints are excluded deliberately: they are a scheduling
    state, not a fault, and folding them in here would make the summary red on
    every idle afternoon.
    """
    return [probe["name"] for probe in probes if probe["reachable"] is False]
