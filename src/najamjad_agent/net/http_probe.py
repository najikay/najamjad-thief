"""Asking the far end an HTTP question, because TCP does not answer the one we have.

`fault_attribution.accepts_tcp` asks whether *something* accepts a connection at
the opponent's address. Against a tunnelled peer that is very nearly a constant,
and we built a verdict on it anyway.

A hosted tunnel has two halves: a cloud edge with a public hostname, and an
agent on the teammate's laptop holding a connection to it. **The edge is up
essentially always.** When the laptop half goes away the edge stays listening on
443, completes the TCP handshake, terminates TLS — and answers HTTP `502` with
the provider's own error page. Our probe saw the handshake succeed, concluded
"their endpoint is reachable; the fault is not connectivity", and stopped one
layer above the only layer where the answer lives.

So this asks at the HTTP layer, and the answer is decisive in **both**
directions, which is the property that makes it worth having:

* a provider error page (`ERR_NGROK_3200`, Cloudflare `1033`, a bare 502/504)
  is the far side's own infrastructure reporting that the far side is gone, and
  is not something we can be accused of manufacturing;
* a `200`, `405` or `406` means their server is answering us perfectly well at
  the moment our MCP client claims it cannot connect — which puts the fault in
  our client, and we should say so first and loudest.

The second branch is the point. A diagnostic that can only exonerate us is not a
diagnostic, and an opponent who has been precise and honest all week would be
right to discard it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Bounded hard: this runs inside a turn that is already failing, and a slow
#: probe would consume the deadline it is trying to explain.
PROBE_TIMEOUT = 3.0
#: Enough of the body to recognise a provider error page, not enough to flood
#: the event log with an HTML document.
BODY_SNIPPET = 300

#: Signatures that mean "the tunnel edge is up and the origin behind it is not".
#: Matched case-insensitively against the body, so a provider rewording its page
#: costs us the signature and not a false accusation.
EDGE_FAILURE_MARKERS = (
    "err_ngrok",
    "tunnel not found",
    "failed to complete tunnel connection",
    "error 1033",
    "error code: 1016",
    "argo tunnel",
    "web server is down",
    "host error",
)
#: Statuses that mean the far origin did not serve the request.
EDGE_FAILURE_STATUSES = frozenset({502, 503, 504, 521, 522, 523, 526, 530})
#: Statuses that mean their server answered us. `405`/`406` are healthy here:
#: a stateless MCP server refuses a bare GET, which is an answer, not an outage.
ALIVE_STATUSES = frozenset({200, 202, 400, 404, 405, 406, 415})


@dataclass(frozen=True)
class ProbeResult:
    """What the far end said when asked directly."""

    reached: bool
    status: int | None = None
    body: str = ""
    error: str = ""

    @property
    def edge_failure(self) -> bool:
        """True when the tunnel answered *for* an origin that is not there."""
        if self.status in EDGE_FAILURE_STATUSES:
            return True
        haystack = self.body.lower()
        return any(marker in haystack for marker in EDGE_FAILURE_MARKERS)

    @property
    def origin_alive(self) -> bool:
        """True when their own server answered, whatever it answered."""
        return self.status in ALIVE_STATUSES and not self.edge_failure

    def as_dict(self) -> dict[str, Any]:
        """Evidence form for the record and the event log."""
        return {
            "reached": self.reached,
            "status": self.status,
            "edge_failure": self.edge_failure,
            "origin_alive": self.origin_alive,
            "body": self.body[:BODY_SNIPPET],
            "error": self.error[:200],
        }


def probe(url: str, timeout: float = PROBE_TIMEOUT) -> ProbeResult:
    """Make one plain HTTP request to `url` and report what came back.

    Input: the opponent's MCP URL.
    Output: a `ProbeResult` — never raises, because this runs on a failure path.
    Setup: none.

    A bare `GET` on purpose. It is the cheapest request that reaches their
    origin, it carries no game payload so it cannot be mistaken for a turn, and
    the `405` a stateless MCP server answers it with is exactly the "your server
    is alive" signal we are looking for.
    """
    if not url:
        return ProbeResult(False, error="no opponent endpoint configured")
    try:
        import httpx

        response = httpx.get(url, timeout=timeout, follow_redirects=True)
    except Exception as error:  # noqa: BLE001 - a failing probe is data, not a crash
        from ..shared.error_detail import describe

        described = describe(error)
        return ProbeResult(False, error=f"{described['error']}: {described['cause']}")
    return ProbeResult(True, status=response.status_code, body=response.text[:BODY_SNIPPET])
