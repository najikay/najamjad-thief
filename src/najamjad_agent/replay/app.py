"""The replay viewer as a second page on the FastAPI stack (ADR-005).

Deliberately self-contained: it reads a file and re-hashes it, and shares
nothing with the live agent. That is what lets it be pointed at an opponent's
log — or at the lecturer's sample — without any of the running game's state
being involved, and it keeps the live dashboard's SDK-only import rule intact.

No hashing happens in the browser. The banner is whatever `domain.audit`
decided; the page renders a verdict it did not compute (T-1910).
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .session import ReplaySession

STATIC = Path(__file__).parent / "static"
FALLBACK_PAGE = "<h1>Replay viewer</h1><p>Viewer assets are missing.</p>"


def register_replay_routes(app: FastAPI, session: ReplaySession) -> None:
    """Attach the viewer's page and read endpoints to an application."""

    @app.get("/replay", response_class=HTMLResponse)
    async def page() -> str:
        """The viewer page itself."""
        source = STATIC / "replay.html"
        return source.read_text(encoding="utf-8") if source.exists() else FALLBACK_PAGE

    @app.get("/api/replay/summary")
    async def summary() -> dict[str, Any]:
        """Banner, verified/failed counts, and the log's metadata."""
        return session.summary()

    @app.get("/api/replay/steps")
    async def steps() -> dict[str, Any]:
        """Every step at once — a whole game is small enough to send."""
        return {"steps": session.steps()}

    @app.get("/api/replay/step/{index}")
    async def step(index: int) -> dict[str, Any]:
        """One step, for forward/back navigation."""
        return session.step(index)

    @app.post("/api/replay/load")
    async def load(body: dict[str, Any]) -> dict[str, Any]:
        """Open a different log file by path."""
        path = str(body.get("path", ""))
        if not path:
            return {"ok": False, "error": "no path supplied"}
        ok = session.load(Path(path))
        return {"ok": ok, "error": session.error, **session.summary()}


def create_replay_app(source: Any = None) -> FastAPI:
    """A standalone viewer application, as the `replay --log` verb opens it."""
    app = FastAPI(title="NajAmjad replay viewer", docs_url=None, redoc_url=None)
    app.state.session = ReplaySession(source)
    register_replay_routes(app, app.state.session)
    if STATIC.exists():
        app.mount("/replay-static", StaticFiles(directory=STATIC), name="replay-static")
    return app
