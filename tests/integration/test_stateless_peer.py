"""Playing a peer whose server is stateless — the shape our own server is not.

Every other transport test talks to `PeerServer`, which is stateful. uoh-sqak's
is not: their whole six-game series shows exactly one `GET /mcp`, answered 405,
because a stateless FastMCP server has no SSE listen stream to offer. That
difference is why three police mini-games died against them and no test here
ever saw it — the double was kinder than the real thing, which is now the fifth
time that has cost us something.

What this pins down:

* a held session survives many calls to a stateless peer, and survives being
  used from a different asyncio task each time — `run_coroutine_threadsafe`
  makes a new task per call, and whether that was the fault was the leading
  theory until it was measured;
* `GET /mcp` really does 405, so the fixture is the thing we mean it to be;
* a peer we cannot connect to surfaces as `RuntimeError` with a *message*, and
  the message is in the event log. fastmcp wraps every connect-level fault as
  `RuntimeError`, so without the message all faults look identical — which is
  precisely how ten retries told us nothing.
"""


import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
from fastmcp import FastMCP

from najamjad_agent.net.mcp_client import PeerClient
from najamjad_agent.net.mcp_server import port_is_free
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig

pytestmark = pytest.mark.slow

TURN = {"step": 1, "sender": "peer-a", "commit": "a" * 64, "hint": "north along the wall"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _client(url: str, events: list[dict]) -> PeerClient:
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=RateLimitConfig(requests_per_minute=600, retry_after_seconds=5, max_retries=2),
        emit=events.append,
        sleep=lambda _seconds: None,
    )
    return PeerClient(url, keeper, emit=events.append, call_timeout=20.0)


def _serve_stateless(port: int) -> threading.Thread:
    """A stateless FastMCP peer: no session id, no listen stream, 405 on GET."""
    server: FastMCP = FastMCP("stateless_peer")

    @server.tool
    def receive_turn(message: dict | None = None, payload: dict | None = None) -> dict:
        return {"accepted": True, "kind": "turn"}

    @server.tool
    def negotiate(message: dict | None = None, payload: dict | None = None) -> dict:
        return {"accepted": True, "kind": "negotiate"}

    thread = threading.Thread(
        target=lambda: server.run(
            transport="http", host="127.0.0.1", port=port, stateless_http=True
        ),
        daemon=True,
    )
    thread.start()
    return thread


@pytest.fixture()
def stateless_url() -> str:
    port = _free_port()
    _serve_stateless(port)
    for _ in range(100):
        if not port_is_free("127.0.0.1", port):
            break
        time.sleep(0.1)
    else:
        pytest.fail("the stateless peer never came up")
    return f"http://127.0.0.1:{port}/mcp"


def test_the_fixture_is_really_stateless(stateless_url: str) -> None:
    """405 on GET is the signature we are modelling; without it this proves nothing."""
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(stateless_url, timeout=5)

    assert raised.value.code == 405


def test_a_held_session_survives_a_run_of_turns_to_a_stateless_peer(stateless_url: str) -> None:
    """Eleven turns is where the real games died; do more than that."""
    events: list[dict] = []
    client = _client(stateless_url, events)
    try:
        for step in range(1, 21):
            client.send("turn", {**TURN, "step": step})
    finally:
        client.close()

    assert sum(event["event"] == "client.sent" for event in events) == 20
    assert client.reconnects == 0, "a stateless peer must not need reconnecting"


def test_one_session_serves_calls_made_from_many_different_tasks(stateless_url: str) -> None:
    """Every call arrives on its own task; the opponent thought that was the bug.

    It is not — but nothing in the suite demonstrated it either way, so the
    theory survived a whole day of debugging. This is the demonstration.
    """
    events: list[dict] = []
    client = _client(stateless_url, events)
    try:
        for step in range(1, 11):
            client.send("turn", {**TURN, "step": step})
    finally:
        client.close()

    opened = [event for event in events if event["event"] == "client.session_opened"]
    assert len(opened) == 1, "the session must be opened once and held"
    assert opened[0]["task"], "the opening task is recorded, so a future failure is readable"


def test_an_unreachable_peer_reports_why_and_not_only_that(stateless_url: str) -> None:
    """`RuntimeError` alone is useless: fastmcp raises it for every connect fault.

    Ten of these ended three police mini-games and named no cause. The type is
    not diagnostic; the message is.
    """
    events: list[dict] = []
    dead = f"http://127.0.0.1:{_free_port()}/mcp"
    client = _client(dead, events)
    try:
        with pytest.raises(RuntimeError):
            client.send("turn", TURN)
    finally:
        client.close()

    failures = [event for event in events if event["event"] == "client.session_failed"]
    assert failures, "a connect that never happened must say so"
    assert failures[0]["detail"], "the message is the only thing that identifies the fault"

    retries = [event for event in events if event["event"] == "gatekeeper.retry"]
    assert retries and all(event["detail"] for event in retries)

    failed = [event for event in events if event["event"] == "gatekeeper.failed"]
    assert failed and failed[0]["detail"], "the final verdict carries the cause too"
