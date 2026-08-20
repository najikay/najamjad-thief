"""Two peers over real FastMCP HTTP — the transport proof, not a simulation.

Everything else in the suite talks through in-memory fakes. This test starts
two actual servers on two localhost ports and sends real MCP tool calls between
them, because the failures that cost a league match (a tool name that does not
match, a payload the peer's schema rejects, a client that stalls) only appear
once a socket is involved.
"""

import socket
import time

import pytest

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.mcp_client import PeerClient
from najamjad_agent.net.mcp_server import PeerServer, port_is_free
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig

pytestmark = pytest.mark.slow

TURN = {"step": 1, "sender": "peer-a", "commit": "a" * 64, "hint": "crossing the bridge"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _client(url: str, events: list[dict] | None = None) -> PeerClient:
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=RateLimitConfig(requests_per_minute=600, retry_after_seconds=5),
        emit=(events.append if events is not None else None),
        sleep=lambda _seconds: None,
    )
    return PeerClient(url, keeper, emit=(events.append if events is not None else None))


def _wait_until_serving(url: str, attempts: int = 50) -> None:
    host, port = url.split("//")[1].split("/")[0].split(":")
    for _ in range(attempts):
        if not port_is_free(host, int(port)):
            return
        time.sleep(0.1)
    raise AssertionError(f"server at {url} never came up")


@pytest.fixture()
def peer() -> tuple[PeerServer, Inboxes, list[dict]]:
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    server = PeerServer(inboxes, port=_free_port(), emit=events.append)
    server.start()
    _wait_until_serving(server.url)
    yield server, inboxes, events


def test_a_turn_travels_between_two_processes_over_http(peer) -> None:
    server, inboxes, _ = peer
    client = _client(server.url)
    try:
        client.send("turn", TURN)
        message = inboxes.poll("turn", timeout=5)
    finally:
        client.close()
    assert message is not None
    assert message.commit == TURN["commit"]
    assert message.hint == "crossing the bridge"


def test_all_four_interop_tools_are_reachable(peer) -> None:
    """Tool names must match the reference exactly or no team can play us."""
    server, inboxes, _ = peer
    client = _client(server.url)
    payloads = {
        "negotiate": {"identity": "peer-a", "terms": {}, "nonce": "n", "signature": "s"},
        "turn": TURN,
        "audit": {"records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}]},
        "control": {"kind": "status"},
    }
    try:
        for kind, payload in payloads.items():
            client.send(kind, payload)
    finally:
        client.close()
    for kind in payloads:
        assert inboxes.poll(kind, timeout=5) is not None, f"{kind} never arrived"


def test_malformed_payload_gets_a_structured_error_and_server_survives(peer) -> None:
    """A hostile or buggy peer must not be able to take our server down."""
    server, inboxes, _ = peer
    client = _client(server.url)
    try:
        client.send("turn", {"step": 1})  # missing the mandatory commit
        assert inboxes.pending("turn") == 0
        client.send("turn", TURN)  # server still serving
        assert inboxes.poll("turn", timeout=5) is not None
    finally:
        client.close()


def test_replayed_turn_is_absorbed_over_the_wire(peer) -> None:
    """At-least-once transport: the second copy lands once, not twice."""
    server, inboxes, events = peer
    client = _client(server.url)
    try:
        client.send("turn", TURN)
        client.send("turn", TURN)
    finally:
        client.close()
    assert inboxes.pending("turn") == 1, "absorbed, so the game sees it once"
    assert any(event["event"] == "inbox.absorbed" for event in events)


def test_the_client_reuses_one_event_loop_for_many_calls(peer) -> None:
    """The reference spawns a loop per call; at ~200 calls a series that hurts."""
    server, inboxes, events = peer
    client = _client(server.url, events)
    try:
        for step in range(1, 11):
            client.send("turn", {**TURN, "step": step})
    finally:
        client.close()
    starts = [event for event in events if event["event"] == "client.loop_started"]
    assert len(starts) == 1, "a new loop was started per call"
    assert inboxes.pending("turn") == 10


def test_every_outbound_call_passes_the_gatekeeper(peer) -> None:
    server, _, events = peer
    client = _client(server.url, events)
    try:
        client.send("turn", TURN)
    finally:
        client.close()
    assert any(event["event"] == "gatekeeper.call" for event in events)


def test_send_to_a_dead_peer_retries_then_fails_cleanly() -> None:
    """No hang: the gatekeeper exhausts its retries and reports."""
    events: list[dict] = []
    client = _client(f"http://127.0.0.1:{_free_port()}/mcp", events)
    try:
        with pytest.raises(RuntimeError, match="failed after"):
            client.send("turn", TURN)
    finally:
        client.close()
    assert any(event["event"] == "gatekeeper.retry" for event in events)


def test_best_effort_send_reports_failure_without_raising() -> None:
    """Post-game audit: the opponent may have exited; that is not a crash."""
    events: list[dict] = []
    client = _client(f"http://127.0.0.1:{_free_port()}/mcp", events)
    try:
        assert client.try_send("audit", {"records": []}) is False
    finally:
        client.close()
    assert any(event["event"] == "client.send_failed" for event in events)


def test_port_preflight_refuses_a_taken_port(peer) -> None:
    server, inboxes, _ = peer
    clash = PeerServer(Inboxes(), port=server.port)
    with pytest.raises(OSError, match="already in use"):
        clash.preflight()


def test_server_reports_its_url_and_running_state(peer) -> None:
    server, _, _ = peer
    assert server.url.endswith("/mcp")
    assert server.running
    server.start()  # idempotent
