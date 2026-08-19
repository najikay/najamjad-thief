"""Serving the dashboard alongside a live match.

The dashboard runs on a daemon thread beside the game rather than in its own
process: it reads the same in-memory SDK the orchestrator is driving, which is
what lets it show belief and turn state without a second source of truth to
disagree with.

A dashboard that fails to start must never stop a match. Losing the window
costs visibility; losing the game costs the league position.
"""

import socket
import threading
from typing import Any

#: Connections a browser may queue while a turn is being computed.
BACKLOG = 16


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

    def _claim(self) -> socket.socket:
        """Take the port on the caller's thread, so a clash is *our* failure.

        uvicorn binds inside `run()`, and on a taken port it logs, calls
        `sys.exit(1)`, and the daemon thread dies alone: `start()` returned True
        with an empty `error`, and the operator was pointed at a URL the
        *sibling* process was serving. In a split match that is not cosmetic. It
        shows one role's board for all six sub-games, which is how our thief
        appeared to start at the corner [0,0] rather than at the agreed [3,3] —
        the panel was the cop's the whole time, correctly labelled `police` in
        its own header, reached through the thief terminal's URL. Binding here
        turns that into a reported failure instead of a silent swap.
        """
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        # Permits a port still in TIME_WAIT from our own last run; a *live*
        # sibling still refuses, which is exactly the case worth reporting.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(BACKLOG)
        return listener

    def start(self) -> bool:
        """Start serving; returns False and records `error` if it cannot.

        Import and launch failures are caught deliberately: this is the one
        subsystem whose absence is survivable, so it reports and steps aside
        rather than propagating into the match.
        """
        if self.running:
            return True
        listener: socket.socket | None = None
        try:
            listener = self._claim()

            import uvicorn

            from .app import create_app

            app = create_app(self._sdk, self._hub)
            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
            server = uvicorn.Server(config)
            self._thread = threading.Thread(
                target=server.run, kwargs={"sockets": [listener]}, name="dashboard", daemon=True
            )
            self._thread.start()
        except Exception as failure:  # noqa: BLE001 - a dead dashboard must not stop play
            if listener is not None:
                # Otherwise a dashboard that failed *after* binding keeps the
                # port, and the sibling process is refused by a dead panel.
                listener.close()
            self.error = f"{type(failure).__name__}: {failure}"
            return False
        return True
