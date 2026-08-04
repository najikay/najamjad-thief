"""The server must not claim to be serving before the socket accepts.

Found from a `cloudflared` log, not from our own: it was filling with

    dial tcp 127.0.0.1:8802: connect: connection refused

against the exact address our tunnel publishes. `start()` returned in 0.4 ms
while the socket did not accept for 314 ms on a cold start, and `running`
answered True for the whole window — so `server.started` fired, the tunnel was
told to go, and `agent.online` announced a URL that refused connections.

An opponent who launches on time and sends their first turn into that window is
refused by us while we are telling them we are ready.
"""

import socket
import threading
import time

import pytest

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.mcp_server import PeerServer, port_is_accepting, port_is_free


def _free_port() -> int:
    """A port nothing is using, released before we return it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture()
def server() -> PeerServer:
    return PeerServer(inboxes=Inboxes(), host="127.0.0.1", port=_free_port())


def test_start_does_not_return_until_the_socket_accepts(server: PeerServer) -> None:
    """The whole fix. Previously `start()` returned ~300 ms too early."""
    server.start()

    assert port_is_accepting(server.host, server.port)


def test_running_means_serving_not_merely_threaded(server: PeerServer) -> None:
    """`running` used to mean `thread.is_alive()`, which is not the same claim."""
    assert not server.running

    server.start()

    assert server.running


def test_the_started_event_fires_only_once_we_can_answer() -> None:
    """Everything downstream keys off this event — the tunnel, `agent.online`.

    Asserted by checking the socket *at the moment the event is published*,
    because the ordering is the entire defect. A test that only checked the
    event was emitted would have passed against the broken code.
    """
    accepting_when_announced: list[bool] = []
    port = _free_port()

    def record(event: dict) -> None:
        if event.get("event") == "server.started":
            accepting_when_announced.append(port_is_accepting("127.0.0.1", port))

    peer = PeerServer(inboxes=Inboxes(), host="127.0.0.1", port=port, emit=record)
    peer.start()

    assert accepting_when_announced == [True]


def test_a_second_start_is_a_no_op(server: PeerServer) -> None:
    """Idempotent, and it must stay so now that `running` does real work."""
    server.start()
    server.start()

    assert server.running


def test_wait_until_ready_gives_up_rather_than_hanging() -> None:
    """A bounded wait, because an unbounded one is a hang wearing a hat."""
    peer = PeerServer(inboxes=Inboxes(), host="127.0.0.1", port=_free_port())

    started = time.monotonic()
    assert peer.wait_until_ready(timeout=0.1) is False
    assert time.monotonic() - started < 2.0


def test_wait_until_ready_returns_early_when_the_serve_thread_died() -> None:
    """Waiting on a dead thread can only ever time out; say so immediately."""
    peer = PeerServer(inboxes=Inboxes(), host="127.0.0.1", port=_free_port())
    peer._thread = threading.Thread(target=lambda: None)  # noqa: SLF001
    peer._thread.start()  # noqa: SLF001
    peer._thread.join()  # noqa: SLF001

    started = time.monotonic()
    assert peer.wait_until_ready(timeout=5.0) is False
    assert time.monotonic() - started < 1.0, "did not notice the thread was dead"


def test_free_and_accepting_are_not_opposites(server: PeerServer) -> None:
    """The distinction the old code collapsed.

    A port can be un-free because something is bound but not yet accepting,
    which is exactly the state that made us announce an address that refused.
    """
    assert port_is_free(server.host, server.port)
    assert not port_is_accepting(server.host, server.port)

    server.start()

    assert not port_is_free(server.host, server.port)
    assert port_is_accepting(server.host, server.port)
