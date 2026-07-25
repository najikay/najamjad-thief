"""Route handlers — every one of them a delegation to the SDK.

There is deliberately no logic here beyond choosing which SDK query answers
which URL. A meta-test enforces that this package imports nothing from the
domain, strategy, net or reporting layers, which is what makes "the UI cannot
show something the rules forbid" a structural property rather than a promise.
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

STATIC = Path(__file__).parent / "static"
FALLBACK_PAGE = "<h1>NajAmjad agent</h1><p>Dashboard assets are missing.</p>"


def register_routes(app: FastAPI, sdk: Any, hub: Any) -> None:
    """Attach every dashboard route to the application."""

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """Serve the single-page dashboard shell."""
        page = STATIC / "index.html"
        return page.read_text(encoding="utf-8") if page.exists() else FALLBACK_PAGE

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        """Liveness for the match-day cockpit and the preflight script."""
        return {"ok": True, "ready": sdk.ready, "viewers": hub.viewers}

    @app.get("/api/snapshot")
    async def snapshot() -> dict[str, Any]:
        """Everything a freshly-opened page needs, in one request."""
        return sdk.snapshot()

    @app.get("/api/events")
    async def events(limit: int = 100) -> dict[str, Any]:
        """Recent events, so a page that connects mid-match is not blank."""
        return {"events": sdk.recent_events(limit)}

    @app.websocket("/ws")
    async def stream(socket: WebSocket) -> None:
        """Push updates as they happen; the client never polls."""
        await hub.join(socket)
        try:
            await socket.send_json({"type": "snapshot", **sdk.snapshot()})
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            hub.leave(socket)
        except Exception:  # noqa: BLE001 - one bad viewer must not take the server down
            hub.leave(socket)
