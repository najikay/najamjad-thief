"""The reconnect path must neither deadlock nor cycle a healthy session.

Both halves are the yamanagh friendly of 2026-08-22, measured from their
access log against ours: 344 requests rejected to 54 served, four session
teardowns, and a `submit_audit` that never arrived.

* `call()` held the class's non-reentrant lock and then invoked `drop()`,
  which takes the same lock — **the reconnect path deadlocked itself on
  every failure**, hanging until `_invoke`'s 25 s timeout cancelled it
  (`client.call_cancelled`, one per attempt in our events).
* `call()` also cycled the session on *any* exception, including a tool that
  ran and answered with an error — against a server that binds one session
  per series, each needless re-initialize was itself rejected, feeding the
  storm their §9.9-shaped complaint described.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp.exceptions import ToolError

from najamjad_agent.net.mcp_session import PeerSession


class _Fake:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.exits = 0

    async def call_tool(self, tool, arguments):
        raise self.error

    async def __aexit__(self, *exc) -> None:
        self.exits += 1


def test_a_transport_failure_reconnects_without_deadlocking(monkeypatch) -> None:
    """The failing call must resolve promptly — not hang to the 25 s cancel."""
    session = PeerSession("http://peer.invalid/mcp", emit=lambda _e: None)
    session._session = _Fake(ConnectionError("socket died"))

    class _DeadClient:
        def __init__(self, url: str) -> None: ...
        async def __aenter__(self):
            raise ConnectionError("still down")

    monkeypatch.setattr("najamjad_agent.net.mcp_session.Client", _DeadClient)

    async def scenario() -> None:
        with pytest.raises(ConnectionError):
            # Two seconds is the deadlock detector: the old code sat on its
            # own lock here until an outside timeout shot it.
            await asyncio.wait_for(session.call("negotiate", {}), timeout=2.0)

    asyncio.run(scenario())
    assert session.reconnects == 1


def test_a_tool_level_error_keeps_the_healthy_session(monkeypatch) -> None:
    """The tool ran; the peer answered. Cycling that session is the storm."""
    session = PeerSession("http://peer.invalid/mcp", emit=lambda _e: None)
    fake = _Fake(ToolError("greeting missing group_id (rule 5)"))
    session._session = fake

    async def scenario() -> None:
        with pytest.raises(ToolError):
            await asyncio.wait_for(session.call("negotiate", {}), timeout=2.0)

    asyncio.run(scenario())
    assert session._session is fake, "the session must survive an app-level rejection"
    assert fake.exits == 0, "and must not be torn down"
    assert session.reconnects == 0
