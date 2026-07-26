"""Our FastMCP server — the four tools every league peer calls.

Tool names and shapes match the reference implementation exactly (ADR-001):
every team starts from the lecturer's repo, so matching it is the cheapest
possible interop.

The tools deliberately contain **no game logic**. They validate and enqueue,
then return immediately. Anything slower would block the caller's HTTP request
inside our decision-making, and any logic here would be logic the orchestrator
does not control.
"""

import socket
import threading
from typing import Any

from fastmcp import FastMCP

from ..shared.events import Emit
from .inbox import Inboxes

SERVER_NAME = "najamjad_peer"


def port_is_free(host: str, port: int) -> bool:
    """True when nothing is already listening on `host:port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def build_server(inboxes: Inboxes, emit: Emit | None = None) -> FastMCP:
    """Create the MCP server exposing the four interop tools."""
    mcp: FastMCP = FastMCP(SERVER_NAME)
    publish = emit or (lambda _event: None)

    def _handle(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate, enqueue, and answer the peer — never raise at them."""
        result = inboxes.accept(kind, payload)
        if not result.ok:
            publish({"event": "server.rejected", "tool": kind, "errors": result.errors})
            return result.error_response(kind)
        return {"accepted": True, "kind": kind}

    @mcp.tool
    def negotiate(payload: dict) -> dict:
        """Receive a signed terms proposal from the opponent."""
        return _handle("negotiate", payload)

    @mcp.tool
    def receive_turn(payload: dict) -> dict:
        """Receive one commit or reveal message."""
        return _handle("turn", payload)

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Receive the opponent's end-of-game revealed records."""
        return _handle("audit", payload)

    @mcp.tool
    def receive_control(payload: dict) -> dict:
        """Receive an out-of-band control instruction."""
        return _handle("control", payload)

    return mcp


class PeerServer:
    """Runs the MCP server on a daemon thread with a preflight port check."""

    def __init__(
        self,
        inboxes: Inboxes,
        host: str = "127.0.0.1",
        port: int = 8802,
        emit: Emit | None = None,
    ) -> None:
        """Bind configuration; nothing starts until `start()` is called."""
        self.host = host
        self.port = port
        self._inboxes = inboxes
        self._emit = emit or (lambda _event: None)
        self._server = build_server(inboxes, emit)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """The MCP endpoint peers should be given."""
        return f"http://{self.host}:{self.port}/mcp"

    @property
    def running(self) -> bool:
        """True while the server thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def preflight(self) -> None:
        """Fail early and actionably if the port is already taken."""
        if not port_is_free(self.host, self.port):
            raise OSError(
                f"port {self.port} on {self.host} is already in use — "
                "stop the other agent or set a different my_port in config"
            )

    def start(self) -> None:
        """Run the server on a daemon thread after preflight (idempotent)."""
        if self.running:
            return
        self.preflight()
        self._emit({"event": "server.starting", "url": self.url})

        def _serve() -> None:
            self._server.run(transport="http", host=self.host, port=self.port, show_banner=False)

        self._thread = threading.Thread(target=_serve, name="mcp-server", daemon=True)
        self._thread.start()
        self._emit({"event": "server.started", "url": self.url})
