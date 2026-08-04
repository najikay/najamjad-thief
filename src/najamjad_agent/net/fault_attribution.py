"""Which side of the wire failed — established at the moment it fails.

A mini-game abandoned because we could not reach the opponent currently records
`end_reason: timeout`, which reads as *we went silent*. That is not neutral: it
accepts blame for an outage on their side of the wire, and the book scores a
technical loss 0/0 for both, so the team that stayed up gets nothing for having
stayed up.

The evidence so far, from real matches, is one-directional: a Cloudflare-hosted
peer played clean; every ngrok-hosted peer showed connection failures; and one
peer with a healthy connection failed for unrelated reasons. Our own endpoint is
a named Cloudflare tunnel and has not been the one to disappear. That is a
pattern, not a proof, which is exactly why this module measures rather than
assumes.

**The test that makes it fair.** When a send fails we immediately ask three
questions: does our own public URL still answer, does their hostname still
resolve, and does their endpoint accept a TCP connection. If our tunnel is
answering and theirs is not, our egress demonstrably worked and the far side is
down. If neither answers, our network is the common factor and the honest
verdict is *ours*. If both answer, the fault is neither reachability nor ours to
name, and it stays `indeterminate`.

Deliberately not a way to win arguments. `indeterminate` is a real verdict and
will be common; a module that concluded "them" whenever it was unsure would be
worth less than nothing in a rules 33-35 dispute, because the first time it was
caught overreaching every other finding would be discounted too.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from . import http_probe
from .readiness import resolves

OPPONENT = "opponent-unreachable"
OURS = "our-network"
INDETERMINATE = "indeterminate"

#: Short: this runs inside a failing turn, and a slow probe would itself cost
#: the deadline we are trying to explain.
PROBE_TIMEOUT = 3.0


@dataclass(frozen=True)
class Attribution:
    """Who failed, and the evidence for saying so."""

    verdict: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """The shape the record and the event log carry."""
        return {"verdict": self.verdict, "detail": self.detail, "evidence": self.evidence}


def _endpoint(url: str) -> tuple[str, int] | None:
    """Host and port from a URL, or None when it is not one."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def accepts_tcp(url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """Whether something accepts a TCP connection at `url`.

    TCP rather than HTTP on purpose: this asks whether the *tunnel edge* is
    there at all, which is the thing that disappears when a free tunnel drops.
    A 4xx or 5xx from a live edge is a different fault and not this one.
    """
    target = _endpoint(url)
    if target is None:
        return False
    try:
        with socket.create_connection(target, timeout=timeout):
            return True
    except OSError:
        return False


def attribute(
    our_url: str,
    their_url: str,
    error: str = "",
    probe: Any = None,
    http: Any = None,
) -> Attribution:
    """Decide who failed, from what is reachable at this moment.

    Input: our public URL, theirs, the failing error's message, and optionally
    overrides for the TCP and HTTP probes.

    Both probes are injectable so a unit test needs no network. That is not
    tidiness: the first version reached the real internet from the suite, and
    a test whose verdict depends on whether an opponent's tunnel happens to be
    up today is a test that will fail for the wrong reason at 20:00.
    Output: an `Attribution` carrying the verdict and the raw observations.
    Setup: none. Safe to call inside a failing turn — every probe is bounded.

    `our_url` empty means we cannot demonstrate our own health, so the verdict
    is `indeterminate` however unreachable they are. Claiming otherwise would be
    exactly the overreach that makes the whole record untrustworthy.
    """
    reach = probe or accepts_tcp
    ask = http or http_probe.probe
    evidence: dict[str, Any] = {"error": error[:200]}
    if not their_url:
        return Attribution(INDETERMINATE, "no opponent endpoint configured", evidence)

    evidence["their_dns"] = resolves(their_url)
    evidence["their_tcp"] = bool(reach(their_url))
    if not our_url:
        return Attribution(INDETERMINATE, "our own endpoint unknown; cannot compare", evidence)
    evidence["our_tcp"] = bool(reach(our_url))

    if evidence["their_tcp"]:
        # A completed TCP handshake is much weaker evidence than it looks. A
        # hosted tunnel is a cloud edge plus an agent on someone's laptop; the
        # edge answers on 443 whether or not the laptop half still exists, so
        # `their_tcp` is very nearly a constant and we built a verdict on it. Ask
        # at the HTTP layer, where the answer actually lives — and where it is
        # decisive in both directions.
        answer = ask(their_url)
        evidence["their_http"] = answer.as_dict()
        if answer.edge_failure:
            return Attribution(
                OPPONENT,
                "their tunnel edge answers but reports no origin behind it",
                evidence,
            )
        if answer.origin_alive:
            return Attribution(
                OURS,
                "their server answered our probe while our own client could not "
                "connect; the fault is on our side",
                evidence,
            )
        return Attribution(
            INDETERMINATE, "their endpoint is reachable; the fault is not connectivity", evidence
        )
    if not evidence["our_tcp"]:
        return Attribution(
            OURS, "neither endpoint answers; our network is the common factor", evidence
        )
    reason = "their host does not resolve" if not evidence["their_dns"] else "their endpoint refused"
    return Attribution(OPPONENT, f"our tunnel answers and {reason}", evidence)
