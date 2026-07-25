"""Persistent MCP client for calling the opponent's tools.

The reference implementation builds a fresh client and a fresh event loop for
*every* call. That is the anti-pattern this module exists to avoid: at ~35
steps per mini-game and 6 mini-games, per-call setup is both latency we cannot
spare inside a 30 s response budget and a reconnection storm the opponent's
server sees as load.

One long-lived event loop on a dedicated thread serves every call, and every
call goes through the `mcp_peer` gatekeeper so retries and backoff obey
`config/rate_limits.json` rather than being reinvented here.
"""

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from fastmcp import Client

from ..shared.gatekeeper import ApiGatekeeper

TOOL_FOR_KIND = {
    "negotiate": "negotiate",
    "turn": "receive_turn",
    "audit": "submit_audit",
    "control": "receive_control",
}


class PeerClient:
    """A persistent connection to one opponent's MCP server."""

    def __init__(
        self,
        opponent_url: str,
        gatekeeper: ApiGatekeeper,
        emit: Callable[[dict], None] | None = None,
        call_timeout: float = 30.0,
    ) -> None:
        """Prepare the client; the loop thread starts on first use."""
        self.opponent_url = opponent_url
        self._gatekeeper = gatekeeper
        self._emit = emit or (lambda _event: None)
        self._timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Start the single background event loop, once."""
        with self._lock:
            if self._loop is not None:
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever, name="mcp-client-loop", daemon=True
            )
            thread.start()
            self._loop, self._thread = loop, thread
            self._emit({"event": "client.loop_started", "url": self.opponent_url})
            return loop

    async def _call_tool(self, tool: str, payload: dict[str, Any]) -> Any:
        """Open a client for this call and invoke `tool`."""
        async with Client(self.opponent_url) as client:
            return await client.call_tool(tool, {"payload": payload})

    def _invoke(self, tool: str, payload: dict[str, Any]) -> Any:
        """Run one tool call on the persistent loop and wait for its result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._call_tool(tool, payload), loop)
        return future.result(timeout=self._timeout)

    def send(self, kind: str, payload: dict[str, Any]) -> Any:
        """Send a message of `kind` to the opponent through the gatekeeper."""
        tool = TOOL_FOR_KIND.get(kind)
        if tool is None:
            raise ValueError(f"unknown message kind {kind!r}")
        self._emit({"event": "client.sending", "tool": tool})
        result = self._gatekeeper.execute(self._invoke, tool, payload)
        self._emit({"event": "client.sent", "tool": tool})
        return result

    def try_send(self, kind: str, payload: dict[str, Any]) -> bool:
        """Best-effort send for audit/control: never raises, always reports.

        Used where the opponent may legitimately have exited already (post-game
        audit exchange); a failure here must not turn a finished game into a
        crash.
        """
        try:
            self.send(kind, payload)
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            self._emit(
                {"event": "client.send_failed", "kind": kind, "error": type(error).__name__}
            )
            return False
        return True

    def close(self) -> None:
        """Stop the background loop (idempotent)."""
        with self._lock:
            loop, thread = self._loop, self._thread
            self._loop, self._thread = None, None
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=2.0)
        self._emit({"event": "client.closed", "url": self.opponent_url})
