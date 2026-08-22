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
from typing import Any

from fastmcp import Client
from fastmcp.exceptions import ToolError

from ..shared.error_detail import describe
from ..shared.events import Emit


def _task_name() -> str:
    """Which asyncio task we are running in, for the event log.

    Every call reaches the background loop through
    `asyncio.run_coroutine_threadsafe`, which wraps it in a *new* task, so the
    task that opens the session is rarely the task that later uses or closes
    it. Whether that matters was the leading theory for a day of lost
    mini-games and could not be settled from the logs, because the logs did not
    say. Now they do. (Names, not `id()`: CPython reuses object ids the moment
    a task is collected, which makes `id()` actively misleading here.)
    """
    task = asyncio.current_task()
    return task.get_name() if task is not None else "no-task"


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
        """The live session, opened once and kept.

        A failure here reaches the caller as `RuntimeError` whatever caused it:
        fastmcp wraps every connect-level fault that way, so "nothing is
        listening", "DNS did not resolve" and "TLS handshake failed" are one
        exception type with three different messages. The failure is evented
        before it propagates, because the alternative — which we lived through —
        is ten identical `RuntimeError` lines and no way to tell which.

        And three *different* messages was the optimistic reading. In the real
        series the wrapper's message was `Client failed to connect: ` with
        nothing after the colon 152 times out of 154, because the exception it
        wrapped stringified to the empty string. `describe` is what makes the
        difference: it follows the wrapper down to whatever actually failed.
        """
        if self._session is None:
            session = Client(self.url)
            try:
                await session.__aenter__()
            except Exception as error:
                self._emit({
                    "event": "client.session_failed",
                    "url": self.url,
                    "task": _task_name(),
                    **describe(error),
                })
                raise
            self._session = session
            self._emit({
                "event": "client.session_opened", "url": self.url, "task": _task_name()
            })
        return self._session

    async def drop(self) -> None:
        """Close and forget the session, tolerating an already-dead socket.

        Takes the lock before claiming the session. `retarget` and `close`
        both drop from outside the request path, and without the lock either can
        `__aexit__` a session out from under a call that is still using it —
        which surfaces as a connect failure against the *old* URL, on a peer we
        had just been told had moved.

        The failure is reported and *then* swallowed, rather than swallowed
        blind. We discard the session either way — a peer that has already gone
        makes an orderly teardown fail by definition — but a teardown that
        silently fails is also how a leaked connection would look, and
        `contextlib.suppress` made that impossible to rule out without a
        purpose-built experiment. It costs one event to never run that
        experiment again.
        """
        async with self._lock:
            await self._drop_locked()

    async def _drop_locked(self) -> None:
        """The teardown itself, for callers already holding the lock.

        `call` is such a caller, and until 2026-08-22 it invoked `drop()`
        instead — which re-acquires the non-reentrant lock this class
        serialises on, so **the reconnect path deadlocked itself on every
        failure**. Each failed call then hung until `_invoke`'s timeout
        cancelled it (`client.call_cancelled`, 25 s burned per attempt), the
        abandoned session was torn down by the *next* attempt's re-initialize,
        and against yamanagh's one-persistent-session server the storm read as
        344 rejected requests against 54 served — their count, our bug.
        """
        session, self._session = self._session, None
        if session is None:
            return
        try:
            await session.__aexit__(None, None, None)
        except Exception as error:  # noqa: BLE001 - reported, then discarded
            self._emit({
                "event": "client.drop_failed",
                "url": self.url,
                "task": _task_name(),
                **describe(error),
            })

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
            except ToolError:
                # The tool RAN — the peer received us, executed, and answered
                # with an error body. The session that carried all of that is
                # demonstrably healthy, and cycling it anyway is how one
                # application-level rejection became a re-initialize storm
                # against a server that binds one session for the series
                # (yamanagh's "reject a second initialize mid-session"). The
                # rejection is the caller's problem; the socket is fine.
                raise
            except Exception as error:  # noqa: BLE001 - one reconnect, then propagate
                await self._drop_locked()
                self.reconnects += 1
                self._emit({
                    "event": "client.reconnecting",
                    "url": self.url,
                    "tool": tool,
                    "task": _task_name(),
                    **describe(error),
                })
                session = await self.open()
                return await session.call_tool(tool, arguments)
