"""Which side of the wire failed, established while it is still failing.

Split out of `MatchRunner` because it is diagnosis rather than match conduct,
and because keeping it there put a `net` import inside the game loop.

Recording `end_reason: timeout` and nothing else reads as *we went silent*,
which quietly accepts blame for an outage on their side. The book scores a
technical loss 0/0 both ways, so the team that stayed up gets nothing for having
stayed up — the record should at least say who did.

Probed now rather than reconstructed later, because a tunnel that dropped for
fifty seconds is answering again by the time anyone reads the report.
"""

from __future__ import annotations

from typing import Any


def live_opponent_url(transport: Any, configured: str) -> str:
    """The address we are *actually* dialling, not the one we were configured with.

    `net/peer_endpoint` moves the client to whatever the peer declared in its
    handshake — that is the whole point of it — while `MatchRunner._urls` holds
    the string read from config at wiring time. Probing the configured one after
    a retarget describes a host we stopped talking to, and since that host is
    usually the dead one we just abandoned, the verdict came back
    `opponent-unreachable` **whatever had actually failed**. Confidently wrong
    blame, written into a graded artifact, from a module whose own docstring
    warns that overreaching once discredits every other finding it makes.
    """
    client = getattr(transport, "client", None)
    return str(getattr(client, "opponent_url", "") or configured or "")


def who_failed(
    urls: tuple[str, str] | None, transport: Any, error: Exception, emit: Any = None
) -> dict[str, Any]:
    """Attribute one failure, or return nothing. Never raises.

    Input: our endpoint and the configured opponent one, the live transport, the
    failing error, and an event sink.
    Output: a `{"fault": {...}}` block to merge into the abandoned record.
    Setup: none.

    This runs inside a failure and must not become a second one.
    """
    publish = emit or (lambda _event: None)
    if urls is None:
        return {}
    try:
        from ..net.fault_attribution import attribute

        ours, configured = urls
        return {"fault": attribute(ours, live_opponent_url(transport, configured), f"{error}").as_dict()}
    except Exception as probe_error:  # noqa: BLE001 - diagnosis is best-effort
        publish({"event": "fault.probe_failed", "error": type(probe_error).__name__})
        return {}
