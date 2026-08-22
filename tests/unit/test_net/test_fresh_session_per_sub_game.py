"""Session lifetime across sub-games: keep it healthy, cycle it dead.

Two peers, two opposite demands, and the history of this file is the swing
between them. imreeyal run one process per sub-game: the socket held through
game N dials a corpse in game N+1, and a tunnel that still accepts TCP hangs
every call to the per-call cap (49 straight read timeouts on 2026-08-12) —
so this file once pinned "drop the session before every window". yamanagh
bind ONE session per client for the whole series and refuse a second
initialize mid-session: that unconditional drop then fed a 400 storm at
every boundary (401 rejected against 176 served, their count) and killed the
windows after the first one, twice.

The resolution: `new_session()` keeps a healthy session; renewal belongs to
the failure paths that can actually see a failure — `PeerSession.call`
reconnects once in-band on a transport error, and a call that burns its full
timeout drops the session on cancellation so the next attempt opens fresh.
Both peers' cases, one mechanism each, no unconditional churn.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.net.mcp_client import PeerClient


class _Session:
    """Stands in for the held MCP session."""

    def __init__(self, url: str, emit: Any = None) -> None:
        self.url = url
        self.connected = True
        self.dropped = False

    async def drop(self) -> None:
        self.dropped = True
        self.connected = False


def _client() -> PeerClient:
    client = PeerClient.__new__(PeerClient)
    client.opponent_url = "http://peer.invalid/mcp"
    client._session = _Session(client.opponent_url)
    client._emit = lambda _event: None
    client._loop = None                       # no loop thread in a unit test
    client._thread = None
    return client


def test_dropping_replaces_the_session_object() -> None:
    client = _client()
    first = client._session

    client.drop_session()

    assert client._session is not first, "a dropped session must be replaced"


def test_dropping_twice_is_harmless() -> None:
    """Idempotent: the second drop has nothing to drop and must not raise."""
    client = _client()
    client.drop_session()
    # The replacement is a real, never-opened PeerSession: connected is
    # already False, which is exactly the second drop's no-op case.
    client.drop_session()


def test_the_transport_keeps_a_healthy_session_across_windows() -> None:
    """The boundary must not cycle a live session — the yamanagh storm."""
    from najamjad_agent.net.peer_transport import PeerTransport

    events: list[dict] = []

    class _Client:
        session_alive = True

        def drop_session(self) -> None:
            raise AssertionError("a healthy session must not be dropped at a boundary")

    transport = PeerTransport.__new__(PeerTransport)
    transport._client = _Client()
    transport._emit = events.append

    transport.new_session()

    assert events and events[0]["event"] == "session.kept"


def test_a_timed_out_call_drops_the_session_for_the_next_attempt() -> None:
    """The imreeyal corpse case, owned by the timeout path now."""
    import time

    client = PeerClient.__new__(PeerClient)
    client.opponent_url = "http://peer.invalid/mcp"
    session = _Session(client.opponent_url)
    client._session = session
    client._emit = lambda _event: None
    client._timeout = 0.05
    client._loop = None
    client._thread = None
    import threading

    client._lock = threading.Lock()

    async def _hang(tool: str, payload: dict) -> None:
        import asyncio

        await asyncio.sleep(10)

    client._call_tool = _hang  # type: ignore[method-assign]

    import contextlib

    with contextlib.suppress(TimeoutError):
        client._invoke("negotiate", {})
    for _ in range(50):                      # the drop is scheduled, not awaited
        if session.dropped:
            break
        time.sleep(0.05)

    assert session.dropped, "a call that burned its cap must cycle the session"
