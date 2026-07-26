"""Holding one MCP session open to the opponent.

Split from `mcp_client` because it is a distinct job with a distinct failure
mode: the client decides *what* to send, this decides whether we still have a
usable connection to send it over.

Opening a session per message costs a connect, an initialize handshake and a
teardown every time — 391 ms against 15 ms on a held session, measured against
our own server. That difference comes straight out of the opponent's 30-second
response deadline, so it is worth holding the socket even though it means
owning its lifecycle.
"""

import asyncio
import contextlib
from typing import Any

from fastmcp import Client

from ..shared.events import Emit


class PeerSession:
    """A single long-lived MCP session, reopened when it dies."""

    def __init__(self, url: str, emit: Emit | None = None) -> None:
        """Nothing connects until the first call."""
        self.url = url
        self.reconnects = 0
        self._emit = emit or (lambda _event: None)
        self._session: Any = None
        # One request at a time. A held session multiplexes nothing: the
        # gatekeeper permits two concurrent calls, and letting both onto the
        # same session interleaved their traffic and stalled the exchange after
        # a couple of messages. Serialising here keeps the win from holding the
        # socket without inventing a protocol on top of it.
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Whether a session is currently held."""
        return self._session is not None

    async def open(self) -> Any:
        """The live session, opened once and kept."""
        if self._session is None:
            session = Client(self.url)
            await session.__aenter__()
            self._session = session
            self._emit({"event": "client.session_opened", "url": self.url})
        return self._session

    async def drop(self) -> None:
        """Close and forget the session, tolerating an already-dead socket."""
        session, self._session = self._session, None
        if session is None:
            return
        # Suppressed deliberately: we are discarding it either way, and a peer
        # that has already gone makes an orderly teardown fail by definition.
        with contextlib.suppress(Exception):
            await session.__aexit__(None, None, None)

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool, reconnecting once if the held session has died.

        Exactly once: peers restart, and the cheapest correct answer to a stale
        socket is a fresh one. A second failure is a real problem and belongs
        to the gatekeeper's retry and backoff policy, not to a loop here.
        """
        async with self._lock:
            try:
                session = await self.open()
                return await session.call_tool(tool, arguments)
            except Exception:  # noqa: BLE001 - one reconnect, then let it propagate
                await self.drop()
                self.reconnects += 1
                self._emit({"event": "client.reconnecting", "url": self.url, "tool": tool})
                session = await self.open()
                return await session.call_tool(tool, arguments)
