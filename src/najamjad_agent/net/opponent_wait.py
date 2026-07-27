"""Waiting for the opponent to come up before we start playing.

Both peers of a match dial each other, and neither can control which of them is
ready first. Without a wait the outcome depends on start order: the peer that
starts first exhausts its retries against a port nobody is listening on and
exits, and the peer that starts second then finds *nothing* — so a rehearsal
against the course reference simulator failed in both directions purely on
timing, before a single game rule ran.

A cold start is ~15 s (importing the MCP stack), so the window is wide enough to
lose every match to it. Two teams agreeing "20:00" will not both be listening at
20:00:00.

The wait is deliberately a **plain TCP probe** rather than an MCP handshake: we
are asking "is anything accepting connections", which is the only question that
has to be answered before the protocol can start. Anything richer would need
their server to be not merely up but agreeable, which is what the game itself is
for.
"""

from __future__ import annotations

import socket
import time
from urllib.parse import urlparse

from ..shared.events import Emit

DEFAULT_PORTS = {"http": 80, "https": 443}


def endpoint_of(url: str) -> tuple[str, int] | None:
    """The (host, port) a URL points at, or None if it names neither."""
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    port = parsed.port or DEFAULT_PORTS.get(parsed.scheme)
    return (parsed.hostname, port) if port else None


def is_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    """Whether something accepts a TCP connection there right now."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_opponent(
    url: str,
    timeout: float = 120.0,
    poll: float = 2.0,
    emit: Emit | None = None,
    clock: object = time.monotonic,
    sleep: object = time.sleep,
) -> bool:
    """Block until the opponent is accepting connections, or the wait expires.

    Returns True if they came up. A False is **not** a forfeit and must not be
    treated as one — it is the caller's cue to tell a human, who can then ask
    the opponent whether they are actually running.
    """
    target = endpoint_of(url)
    announce = emit or (lambda _event: None)
    if target is None:
        announce({"event": "opponent.wait_skipped", "reason": "no host in opponent_url"})
        return False

    host, port = target
    started = clock()  # type: ignore[operator]
    announced = False
    while clock() - started < timeout:  # type: ignore[operator]
        if is_listening(host, port):
            announce({"event": "opponent.ready", "waited": round(clock() - started, 1)})  # type: ignore[operator]
            return True
        if not announced:
            # Once, not every poll: a human watching the console needs to know
            # we are waiting rather than stuck, and needs it said once.
            announce({"event": "opponent.waiting", "host": host, "port": port})
            announced = True
        sleep(poll)  # type: ignore[operator]
    announce({"event": "opponent.absent", "host": host, "port": port, "waited": timeout})
    return False
