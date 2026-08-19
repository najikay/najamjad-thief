"""Our FastMCP server — the four tools every league peer calls.

Tool names and shapes match the reference implementation exactly (ADR-001):
every team starts from the lecturer's repo, so matching it is the cheapest
possible interop.

The tools deliberately contain **no game logic**. They validate and enqueue,
then return immediately. Anything slower would block the caller's HTTP request
inside our decision-making, and any logic here would be logic the orchestrator
does not control.
"""

import threading
from typing import Any

from fastmcp import FastMCP

from ..shared.events import Emit
from .inbox import Inboxes
from .readiness import (
    READY_TIMEOUT_SECONDS,
    port_is_accepting,
    port_is_free,
    wait_until_accepting,
)

SERVER_NAME = "najamjad_peer"


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
        answer: dict[str, Any] = {"accepted": True, "kind": kind}
        # Ride our own agreement back on their connection. Additive and ignored
        # by any peer that does not look for it — the reference tolerates
        # unknown response fields exactly as it tolerates unknown request ones.
        if kind == "negotiate" and inboxes.our_agreement is not None:
            answer["agreement"] = inboxes.our_agreement
        return answer

    def _body(message: dict | None, payload: dict | None) -> dict:
        """Whichever argument name the caller used.

        The reference implementation names this argument `message` on three
        tools and `payload` on `submit_audit`, and its client sends exactly
        that. We accepted only `payload`, so a reference-derived opponent —
        which is most of the class — could not deliver a single turn to us, and
        we could not deliver one to them. Verified against the real simulator,
        in both directions, before and after this change.

        Accepting both names costs nothing and makes us the peer that works.
        """
        body = message if message is not None else payload
        return body if isinstance(body, dict) else {}

    @mcp.tool
    def negotiate(message: dict | None = None, payload: dict | None = None) -> dict:
        """Receive a signed terms proposal from the opponent."""
        return _handle("negotiate", _body(message, payload))

    @mcp.tool
    def receive_turn(message: dict | None = None, payload: dict | None = None) -> dict:
        """Receive one commit or reveal message."""
        return _handle("turn", _body(message, payload))

    @mcp.tool
    def submit_audit(payload: dict | None = None, message: dict | None = None) -> dict:
        """Receive the opponent's end-of-game revealed records."""
        return _handle("audit", _body(message, payload))

    @mcp.tool
    def receive_control(message: dict | None = None, payload: dict | None = None) -> dict:
        """Receive an out-of-band control instruction."""
        return _handle("control", _body(message, payload))

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
        """True while the server is actually accepting connections.

        This used to mean "the thread is alive", which is not the same thing and
        the difference cost us mini-games. `threading.Thread.start()` returns as
        soon as the thread is *scheduled*; uvicorn then imports, builds the app
        and binds — 314 ms on a cold start here. For that whole window the thread
        was alive, `running` said True, `server.started` had been emitted, the
        tunnel had been told to go, and `agent.online` had announced a URL that
        answered **connection refused**.

        That is not a theoretical window. Our own `cloudflared` log fills with
        `dial tcp 127.0.0.1:8802: connect: connection refused` against exactly
        this address, and an opponent who launches on time and sends their first
        turn into it gets refused by us while we are telling them we are ready.
        """
        return (
            self._thread is not None
            and self._thread.is_alive()
            and port_is_accepting(self.host, self.port)
        )

    def wait_until_ready(self, timeout: float = READY_TIMEOUT_SECONDS) -> bool:
        """Block until the socket accepts, the thread dies, or `timeout` passes."""
        return wait_until_accepting(
            self.host,
            self.port,
            timeout,
            alive=lambda: self._thread is None or self._thread.is_alive(),
        )

    def preflight(self) -> None:
        """Fail early and actionably if the port is already taken."""
        if not port_is_free(self.host, self.port):
            raise OSError(
                f"port {self.port} on {self.host} is already in use — "
                "stop the other agent or set a different my_port in config"
            )

    def start(self) -> None:
        """Serve on a daemon thread and **wait until the socket accepts**.

        The wait is the point. `server.started` is now emitted only once a real
        TCP connection succeeds, so every downstream consequence of that
        event — the tunnel starting, `agent.online`, telling an opponent we are
        ready — happens after we can actually answer.

        A start that never becomes ready raises rather than returning quietly.
        An agent that believes it is serving and is not will wait out the whole
        match on turns that were refused at the door, which is a far more
        expensive failure than refusing to start.
        """
        if self.running:
            return
        self.preflight()
        self._emit({"event": "server.starting", "url": self.url})

        def _serve() -> None:
            self._server.run(transport="http", host=self.host, port=self.port, show_banner=False)

        self._thread = threading.Thread(target=_serve, name="mcp-server", daemon=True)
        self._thread.start()
        if not self.wait_until_ready():
            self._emit({"event": "server.never_ready", "url": self.url})
            raise OSError(
                f"MCP server did not accept connections on {self.host}:{self.port} "
                f"within {READY_TIMEOUT_SECONDS:.0f}s — the tunnel would have "
                "published an address that answers connection refused"
            )
        self._emit({"event": "server.started", "url": self.url})
