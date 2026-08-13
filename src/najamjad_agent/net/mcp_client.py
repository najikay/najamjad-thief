"""Persistent MCP client for calling the opponent's tools.

The reference implementation builds a fresh client and a fresh event loop for
*every* call. That is the anti-pattern this module exists to avoid: at ~35
steps per mini-game and 6 mini-games, per-call setup is both latency we cannot
spare inside a 30 s response budget and a reconnection storm the opponent's
server sees as load.

We only half avoided it. The event loop was long-lived from the start, but the
MCP *session* was opened and torn down per call, so every message still paid a
connect and an initialize handshake — 391 ms against 15 ms on a held session,
measured. Both are long-lived now.

One long-lived event loop on a dedicated thread serves every call, and every
call goes through the `mcp_peer` gatekeeper so retries and backoff obey
`config/rate_limits.json` rather than being reinvented here.
"""

import asyncio
import contextlib
import threading
from typing import Any

from ..shared.events import Emit
from ..shared.gatekeeper import ApiGatekeeper
from .best_effort import try_send as best_effort_send
from .mcp_session import PeerSession
from .tool_names import ARGUMENT_FOR_TOOL, TOOL_FOR_KIND


class PeerClient:
    """A persistent connection to one opponent's MCP server."""

    def __init__(
        self,
        opponent_url: str,
        gatekeeper: ApiGatekeeper,
        emit: Emit | None = None,
        # Strictly under the signed 30 s response deadline, never equal to it:
        # the cap has to leave room for a retry to complete inside the deadline.
        # `build_transport` passes the configured value and refuses a config
        # where it is not under the deadline; this default matches it so a
        # directly-constructed client is not the one place that still breaches.
        call_timeout: float = 10.0,
    ) -> None:
        """Prepare the client; the loop thread starts on first use."""
        self.opponent_url = opponent_url
        self._gatekeeper = gatekeeper
        self._emit = emit or (lambda _event: None)
        self._timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._session = PeerSession(opponent_url, emit=self._emit)

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
        """Invoke `tool` on the opponent over a session we keep open.

        One session, not one per message. Opening a fresh MCP session per call
        costs a connect, an initialize handshake and a teardown every time —
        measured at 391 ms against 15 ms on a held session, a 25x difference,
        and time spent there is time taken out of the opponent's 30-second
        deadline for no benefit.

        A dropped session is retried exactly once: peers restart, and the
        cheapest correct answer to a stale socket is a new one. A second
        failure is a real problem and belongs to the gatekeeper's retry policy.

        Conservative in what we send: exactly the argument name the reference
        declares for this tool. Our own server accepts either.
        """
        argument = ARGUMENT_FOR_TOOL.get(tool, "payload")
        return await self._session.call(tool, {argument: payload})

    def _invoke(self, tool: str, payload: dict[str, Any]) -> Any:
        """Run one tool call on the persistent loop and wait for its result.

        A timeout **cancels** the coroutine rather than abandoning it: an
        abandoned call keeps holding `PeerSession._lock`, so every gatekeeper
        retry then blocks on it and burns its own full timeout. Against a peer
        whose edge accepts TCP and never answers — the ngrok case we have
        already lost games to — that is ten retries at thirty seconds, minutes
        past the point their watchdog scored the turn against us.
        """
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._call_tool(tool, payload), loop)
        try:
            return future.result(timeout=self._timeout)
        except TimeoutError:
            future.cancel()
            self._emit({"event": "client.call_cancelled", "tool": tool, "url": self.opponent_url})
            raise

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
        """Best-effort send for audit and control (see `net/best_effort.py`)."""
        return best_effort_send(self, kind, payload, self._emit)

    def close(self) -> None:
        """Release the session, then stop the background loop (idempotent).

        Session first: it lives on that loop, so closing it afterwards would
        have nothing left to run on and would leak the opponent's socket.
        """
        self._release_session()
        with self._lock:
            loop, thread = self._loop, self._thread
            self._loop, self._thread = None, None
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=2.0)
        self._emit({"event": "client.closed", "url": self.opponent_url})

    def _release_session(self) -> None:
        """Close the held MCP session if one was ever opened."""
        loop = self._loop
        if loop is None or not self._session.connected:
            return
        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(self._session.drop(), loop).result(timeout=5)

    # Correctness at a sub-game boundary, not hygiene. Against a peer running
    # each sub-game as its own process, a reused session dials a corpse: nothing
    # refuses, every call hangs to the per-call cap, and a bare `curl` reads a
    # healthy 406 off their *new* process meanwhile — so the tunnel and the peer
    # both look fine and only the session is dead. It cost a whole friendly on
    # 2026-08-12. Full story in tests/unit/test_net/test_fresh_session_per_sub_game.py
    def drop_session(self) -> None:
        """Release the held session so the next call opens a fresh one."""
        if not self._session.connected:
            return
        self._release_session()
        self._session = PeerSession(self.opponent_url, emit=self._emit)
        self._emit({"event": "client.session_dropped", "url": self.opponent_url})

    def retarget(self, opponent_url: str) -> None:
        """Move to a new opponent address, dropping the session held on the old one.

        Input: the URL the peer declared in its handshake.
        Output: none; subsequent calls go to the new address.
        Setup: none. Safe before the loop has started.

        The old session must be released rather than abandoned. It is an open
        socket to a host we are done with, and on a peer whose tunnel re-mints
        every session — which is the case this exists for — that host is usually
        already gone, so keeping it costs a file descriptor and an event loop
        callback for the rest of the series.

        The loop itself is *not* restarted. It is address-agnostic and restarting
        it would throw away the one long-lived thing this class exists to keep.
        """
        if not opponent_url or opponent_url == self.opponent_url:
            return
        self._release_session()
        self.opponent_url = opponent_url
        self._session = PeerSession(opponent_url, emit=self._emit)

    @property
    def reconnects(self) -> int:
        """How many times the session had to be re-established."""
        return self._session.reconnects
