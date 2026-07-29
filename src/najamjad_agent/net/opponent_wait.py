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

The wait was originally a **plain TCP probe**, on the reasoning that "is
anything accepting connections" is the only question that must be answered
before the protocol starts. That reasoning is wrong the moment the opponent is
behind a tunnel, which is how every real match is played.

A Cloudflare edge accepts TCP on :443 whether or not the agent behind it is
running — a dead origin answers `502`, but only at the HTTP layer. So the probe
returned True instantly against an opponent who was not there, the wait passed,
and the very first handshake died with `502 Bad Gateway`. The one guard built
for this race was inert precisely in the configuration it exists for.

So an `http(s)` URL is probed with a real request, and anything below `500` is
taken as ready: `400 Missing session ID` means their MCP server is up and
talking, which is all we need to know. A `5xx` is the tunnel telling us the
origin is down. Bare `host:port` targets keep the TCP probe, which is exact for
them.
"""

from __future__ import annotations

import socket
import time
from urllib.parse import urlparse

from ..shared.events import Emit

DEFAULT_PORTS = {"http": 80, "https": 443}
#: How often to say we are still waiting. Silence for fifteen minutes reads as
#: a hang, and an operator who suspects a hang restarts the working process.
NOTE_EVERY_SEC = 60.0


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


def answers_http(url: str, timeout: float = 5.0) -> bool:
    """Delegate to the one egress module (ADR-009); see `endpoint_answers`."""
    from .mcp_probe import endpoint_answers

    return endpoint_answers(url, timeout=timeout)


def is_ready(url: str, host: str, port: int, timeout: float = 5.0) -> bool:
    """Ready by the strongest check the target supports."""
    if url.startswith(("http://", "https://")):
        return answers_http(url, timeout=timeout)
    return is_listening(host, port)


def wait_for_opponent(
    url: str,
    timeout: float = 900.0,
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
    last_note = 0.0
    announced = False
    while clock() - started < timeout:  # type: ignore[operator]
        if is_ready(url, host, port):
            announce({"event": "opponent.ready", "waited": round(clock() - started, 1)})  # type: ignore[operator]
            return True
        if not announced or clock() - last_note >= NOTE_EVERY_SEC:  # type: ignore[operator]
            # Once immediately, then every minute. A single line at the start
            # was right for a two-minute wait and wrong for a fifteen-minute
            # one: fourteen silent minutes is indistinguishable from a hang,
            # and an operator who suspects a hang restarts the thing that was
            # working.
            announce({
                "event": "opponent.waiting",
                "host": host,
                "port": port,
                "waited": round(clock() - started, 0),  # type: ignore[operator]
                "giving_up_in": round(timeout - (clock() - started), 0),  # type: ignore[operator]
            })
            last_note = clock()  # type: ignore[operator]
            announced = True
        sleep(poll)  # type: ignore[operator]
    announce({"event": "opponent.absent", "host": host, "port": port, "waited": timeout})
    return False
