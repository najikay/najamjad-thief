"""Sending something whose failure must not end the game.

Split out of `PeerClient` because it is a *policy*, not a transport concern, and
the distinction is easy to lose: the core send path propagates failures so the
gatekeeper can retry and the match runner can score a technical outcome, while
the post-game audit exchange must not turn a finished game into a crash.

The opponent may legitimately have exited by then — they scored the game, filed
their report and stopped — so a failure here is expected traffic, not a fault.
It is reported rather than swallowed, because a silent failure to deliver an
audit is indistinguishable from never having tried.
"""

from __future__ import annotations

from typing import Any


def try_send(client: Any, kind: str, payload: dict[str, Any], emit: Any = None) -> bool:
    """Send `kind` and report whether it landed; never raises.

    Input: the peer client, the message kind, its payload, and an event sink.
    Output: True when the send completed.
    Setup: none.
    """
    publish = emit or (lambda _event: None)
    try:
        client.send(kind, payload)
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        publish({"event": "client.send_failed", "kind": kind, "error": type(error).__name__})
        return False
    return True
