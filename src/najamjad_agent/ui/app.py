"""The dashboard server — push, not poll.

Assignment 6's UI polled REST endpoints on a timer, which is what made it feel
clunky and what dropped updates under load. Here the event bus is the only
source: a subscriber pushes each event to every connected socket the moment it
is published, and the browser's only timer is a reconnect backoff.

This module owns wiring and fan-out. Routes live in `views`, frame shapes in
`frames`, and all data comes from the SDK — see `views` for why that boundary
matters.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .frames import validate_frame
from .views import STATIC, register_routes


class ConnectionHub:
    """Tracks live dashboard sockets and fans events out to them."""

    def __init__(self) -> None:
        """Start with no viewers and no loop bound yet."""
        self._sockets: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self.dropped = 0
        self.invalid = 0

    @property
    def viewers(self) -> int:
        """How many dashboards are currently connected."""
        return len(self._sockets)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server loop so the game thread can schedule sends."""
        self._loop = loop

    async def join(self, socket: WebSocket) -> None:
        """Accept a new dashboard connection."""
        await socket.accept()
        self._sockets.append(socket)

    def leave(self, socket: WebSocket) -> None:
        """Drop a closed connection; safe to call twice."""
        if socket in self._sockets:
            self._sockets.remove(socket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send to every viewer, dropping any that have gone away.

        Each socket is sent to independently, so one slow or dead viewer costs
        the others nothing but its own failed send.

        A frame that fails validation is dropped, never sent: the guard exists
        to stop a forbidden field reaching a browser, so "send it anyway" is
        the one response that is never right. Drops are counted rather than
        silent, because a panel that stops updating with no trace is the A6
        failure mode this whole layer was built to avoid.
        """
        try:
            frame = validate_frame(message)
        except (ValueError, ValidationError):
            self.invalid += 1
            return
        for socket in list(self._sockets):
            try:
                await socket.send_json(frame)
            except Exception:  # noqa: BLE001 - a dead viewer must not stop the game
                self.dropped += 1
                self.leave(socket)

    def publish(self, event: dict[str, Any]) -> None:
        """Bus subscription entry point, called from the game thread.

        The game runs on its own thread while the server owns the loop, so the
        send is scheduled across rather than awaited here; with no viewers or no
        loop there is nothing to do and the game proceeds untouched.
        """
        if self._loop is None or not self._sockets:
            return
        # `type` last: an event that happens to carry its own `type` field would
        # otherwise rename the frame, and the renamed frame fails validation and
        # vanishes. The bus belongs to the game, so it may legitimately publish
        # any keys it likes; the envelope is ours and must win.
        asyncio.run_coroutine_threadsafe(
            self.broadcast({**event, "type": "event"}), self._loop
        )


def create_app(sdk: Any, hub: ConnectionHub | None = None) -> FastAPI:
    """Build the dashboard application around an SDK instance."""
    live = hub or ConnectionHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Bind the running loop so the game thread can schedule sends onto it."""
        live.bind_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(
        title="NajAmjad agent dashboard", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.sdk = sdk
    app.state.hub = live
    register_routes(app, sdk, live)

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def attach_bus(bus: Any, hub: ConnectionHub) -> Any:
    """Subscribe the hub to the event bus; returns the unsubscribe callable."""
    return bus.subscribe(hub.publish)
