"""Asking whether a socket is actually there, which is not one question.

Split out of `mcp_server` because collapsing two different questions into one
predicate is what let us publish a tunnel address that answered `connection
refused`:

* `port_is_free` asks **can I bind here** — the pre-start check, so two agents
  do not fight over 8802.
* `port_is_accepting` asks **will a connection complete** — the post-start
  check, and *not* the negation of the first. Between them lies the window
  where a socket is bound but the server has not begun accepting, which is
  where a cold start spends its first ~300 ms.

Our `cloudflared` log is full of `dial tcp 127.0.0.1:8802: connect: connection
refused` against exactly that window.
"""

from __future__ import annotations

import socket
import threading
import time
from urllib.parse import urlparse

#: How long to wait for a server to come up before calling it a failure.
READY_TIMEOUT_SECONDS = 10.0
#: Poll interval while waiting; short enough not to delay a fast start.
READY_POLL_SECONDS = 0.02
#: Per-attempt connect timeout. Generous for loopback, still bounded.
PROBE_TIMEOUT_SECONDS = 0.2


def port_is_free(host: str, port: int) -> bool:
    """True when nothing is already bound to `host:port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def port_is_accepting(host: str, port: int, timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """True when a TCP handshake to `host:port` actually completes."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_until_accepting(
    host: str,
    port: int,
    timeout: float = READY_TIMEOUT_SECONDS,
    alive: object = None,
) -> bool:
    """Block until `host:port` accepts, the server dies, or `timeout` elapses.

    Input: the address, how long to wait, and optionally a zero-argument
    predicate reporting whether the server is still alive.
    Output: True only when a connection genuinely succeeded.
    Setup: none.

    `alive` exists so waiting on a server that has already crashed returns at
    once instead of burning the full timeout — the answer is known, and a caller
    blocked for ten seconds on a settled question is a hang wearing a hat.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(alive) and not alive():
            return False
        if port_is_accepting(host, port):
            return True
        time.sleep(READY_POLL_SECONDS)
    return False


def resolves(url: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """Whether the host in `url` resolves in DNS right now.

    Bounded by running the lookup on its own thread and refusing to wait past
    `timeout`, because the obvious approach does not work and we shipped it:
    `socket.setdefaulttimeout` is **process-global and was never restored**, so
    every socket created anywhere in the agent afterwards inherited a 3-second
    timeout for the rest of the match — and `getaddrinfo` does not honour it
    anyway, since the resolver keeps its own. The docstring on `attribute`
    promised every probe was bounded; on the one failure this module exists for,
    a hostname that has stopped resolving, it could block for the resolver's
    full retry budget inside an already-failing turn.

    A daemon thread left behind by a timeout costs one thread until the resolver
    gives up, which is bounded and harmless; blocking the turn is not.
    """
    target = _host_and_port(url)
    if target is None:
        return False
    found: list[bool] = []

    def _lookup() -> None:
        try:
            socket.getaddrinfo(target[0], target[1], proto=socket.IPPROTO_TCP)
        except OSError:
            found.append(False)
        else:
            found.append(True)

    worker = threading.Thread(target=_lookup, name="dns-probe", daemon=True)
    worker.start()
    worker.join(timeout)
    return bool(found and found[0])


def _host_and_port(url: str) -> tuple[str, int] | None:
    """Host and port from a URL, or None when it is not one."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
