"""Serving the dashboard alongside a live match.

The dashboard runs on a daemon thread beside the game rather than in its own
process: it reads the same in-memory SDK the orchestrator is driving, which is
what lets it show belief and turn state without a second source of truth to
disagree with.

A dashboard that fails to start must never stop a match. Losing the window
costs visibility; losing the game costs the league position.
"""

import threading
from typing import Any


class DashboardServer:
    """Runs the UI on a daemon thread, and never takes the game down with it."""

    def __init__(self, sdk: Any, hub: Any, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Bind configuration; nothing starts until `start()`."""
        self.host = host
        self.port = port
        self.error = ""
        self._sdk = sdk
        self._hub = hub
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """Where an operator should point their browser."""
        return f"http://{self.host}:{self.port}/"

    @property
    def running(self) -> bool:
        """True while the server thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start serving; returns False and records `error` if it cannot.

        Import and launch failures are caught deliberately: this is the one
        subsystem whose absence is survivable, so it reports and steps aside
        rather than propagating into the match.
        """
        if self.running:
            return True
        try:
            import uvicorn

            from .app import create_app

            app = create_app(self._sdk, self._hub)
            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
            server = uvicorn.Server(config)
            self._thread = threading.Thread(target=server.run, name="dashboard", daemon=True)
            self._thread.start()
        except Exception as failure:  # noqa: BLE001 - a dead dashboard must not stop play
            self.error = f"{type(failure).__name__}: {failure}"
            return False
        return True
