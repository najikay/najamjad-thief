"""Route handlers — every one of them a delegation to the SDK.

There is deliberately no logic here beyond choosing which SDK query answers
which URL. A meta-test enforces that this package imports nothing from the
domain, strategy, net or reporting layers, which is what makes "the UI cannot
show something the rules forbid" a structural property rather than a promise.
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..sdk.match_history import match_history, standings
from .controls import (
    ControlDeniedError,
    approve_terms,
    negotiation_state,
    peer_state,
    start_peer,
    stop_peer,
)
from .frames import validate_frame

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

    @app.get("/api/matches")
    async def matches() -> dict[str, Any]:
        """Every match we have filed, plus our standing as the artifacts describe it.

        Read back from the `result_*.json` files we emailed, so what an operator
        sees here is what the lecturer received — not a second account that
        could quietly disagree with it.
        """
        from ..sdk.app_paths import history_roots, our_group

        history = match_history(*history_roots())
        return {"matches": history, "standings": standings(history, our_group())}

    @app.get("/api/cockpit")
    async def cockpit() -> dict[str, Any]:
        """Match-day readiness in one request (T-1819).

        Deliberately read-only. Starting a match from a browser tab would put a
        graded action one stray click away, and the runbook is the interface for
        that.
        """
        return sdk.cockpit()

    @app.get("/api/control")
    async def control_state() -> dict[str, Any]:
        """What the server believes, so the page never paints its own guess."""
        return {"peer": peer_state(sdk), "negotiation": negotiation_state(sdk)}

    @app.post("/api/control/peer")
    async def control_peer(body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start or stop serving — reversible, so safe behind a button.

        Playing a counted match is deliberately absent: it is graded and cannot
        be undone, and `docs/RUNBOOK.md` is the interface for it.
        """
        action = str((body or {}).get("action", ""))
        try:
            if action == "start":
                return start_peer(sdk)
            if action == "stop":
                return stop_peer(sdk)
        except ControlDeniedError as denied:
            raise HTTPException(status_code=403, detail=str(denied)) from denied
        raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'")

    @app.post("/api/control/approve")
    async def control_approve(body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Sign terms a person has read (FR-NEG-4)."""
        payload = body or {}
        try:
            return approve_terms(sdk, payload.get("terms") or {}, payload.get("identity"))
        except ControlDeniedError as denied:
            raise HTTPException(status_code=403, detail=str(denied)) from denied

    @app.websocket("/ws")
    async def stream(socket: WebSocket) -> None:
        """Push updates as they happen; the client never polls."""
        await hub.join(socket)
        try:
            # Validated like every other frame. This one carries the whole
            # board, so exempting it would have left the largest payload as the
            # only one the local-truth guard never sees (book rules 8-9).
            await socket.send_json(validate_frame({**sdk.snapshot(), "type": "snapshot"}))
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            hub.leave(socket)
        except Exception:  # noqa: BLE001 - one bad viewer must not take the server down
            hub.leave(socket)
