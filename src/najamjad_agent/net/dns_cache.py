"""Resolve the opponent once, then stop asking — DNS was losing us games.

Three mini-games against uoh-sqak died to this, and the message that finally
named it was one line in fifty:

    client.session_failed: Client failed to connect:
        [Errno -3] Temporary failure in name resolution

Not their server: the attribution probe found their endpoint reachable seconds
later, every time. Not the session object either, which was the opponent's
theory — `open()` already builds a fresh `Client`, and this fails *before* a
session exists. It is our own resolver, and it is measurably fragile: a median
lookup of 502 ms and a worst case of 1.9 s on this machine, where healthy is
under 50. Under load it stops being slow and starts failing outright.

It looked like an ngrok problem because ngrok hands out long random hostnames
that need a fresh public lookup on every reconnect, while a named Cloudflare
tunnel resolves once and stays cached. Same weakness, different exposure — the
peers who "worked" were the ones whose names we only had to resolve once.

So we resolve once and hold it. A match is minutes long and an opponent's
address does not move inside one, so re-querying mid-game buys nothing and
costs mini-games.

**Failures are never cached.** A host that is genuinely down must keep failing,
or a peer who starts late could never be reached at all — caching a negative
would turn a recoverable "not up yet" into a permanent one.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

#: How long a resolved address stays good. Comfortably longer than a series and
#: far shorter than a session, so a genuinely moved host recovers on its own.
DEFAULT_TTL = 1800.0

_lock = threading.Lock()
_entries: dict[tuple, tuple[float, Any]] = {}
_original: Any = None


def _cached_getaddrinfo(host, port, *args, **kwargs):
    """`socket.getaddrinfo` with successful answers remembered."""
    key = (host, port, args, tuple(sorted(kwargs.items())))
    now = time.monotonic()
    with _lock:
        hit = _entries.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    # Resolved outside the lock: a slow lookup must not block every other
    # caller, which on a 1.9 s worst case would be its own kind of outage.
    answer = _original(host, port, *args, **kwargs)
    with _lock:
        _entries[key] = (now + _ttl, answer)
    return answer


_ttl = DEFAULT_TTL


def install(ttl: float = DEFAULT_TTL) -> bool:
    """Start remembering DNS answers process-wide. True when newly installed.

    Idempotent: installing twice would wrap the wrapper and make the original
    unrecoverable, so the second call is a no-op.
    """
    global _original, _ttl
    _ttl = ttl
    if _original is not None:
        return False
    _original = socket.getaddrinfo
    socket.getaddrinfo = _cached_getaddrinfo  # type: ignore[assignment]
    return True


def uninstall() -> None:
    """Restore the real resolver and forget everything. For tests."""
    global _original
    with _lock:
        _entries.clear()
    if _original is not None:
        socket.getaddrinfo = _original  # type: ignore[assignment]
        _original = None


def warm(url: str, emit: Any = None) -> bool:
    """Resolve `url`'s host now, so the first turn does not pay for it.

    Input: any URL; a bare host works too. Output: whether it resolved.
    Setup: `install()` should already have run, or this warms nothing.

    Called at match start. Failing here is not fatal — the opponent may simply
    not be up yet — but it is worth an event, because a name that will not
    resolve before the match is a name that will not resolve during it.
    """
    from urllib.parse import urlparse

    host = urlparse(url).hostname if "//" in url else url
    if not host:
        return False
    publish = emit or (lambda _event: None)
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as error:
        publish({"event": "dns.warm_failed", "host": host, "error": f"{error}"})
        return False
    publish({"event": "dns.warmed", "host": host})
    return True


def cached_hosts() -> int:
    """How many answers we are currently holding, for the dashboard."""
    with _lock:
        return len(_entries)
