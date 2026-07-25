"""Unit tests for the persistent MCP client's contract and lifecycle."""

import pytest

from najamjad_agent.net.mcp_client import TOOL_FOR_KIND, PeerClient
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig

UNUSED_URL = "http://127.0.0.1:1/mcp"


def _client(events: list[dict] | None = None) -> PeerClient:
    sink = events.append if events is not None else None
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=RateLimitConfig(requests_per_minute=600, max_retries=1),
        emit=sink,
        sleep=lambda _seconds: None,
    )
    return PeerClient(UNUSED_URL, keeper, emit=sink)


def test_kind_to_tool_mapping_matches_the_reference_names() -> None:
    """These four names are the whole interop contract (ADR-001)."""
    assert TOOL_FOR_KIND == {
        "negotiate": "negotiate",
        "turn": "receive_turn",
        "audit": "submit_audit",
        "control": "receive_control",
    }


def test_an_unknown_kind_is_refused_before_any_network_call() -> None:
    client = _client()
    with pytest.raises(ValueError, match="unknown message kind"):
        client.send("gossip", {})


def test_close_without_use_is_safe() -> None:
    """Nothing was started, so nothing needs stopping."""
    client = _client()
    client.close()
    client.close()


def test_the_event_loop_starts_once_and_stops_cleanly() -> None:
    events: list[dict] = []
    client = _client(events)
    first = client._ensure_loop()
    second = client._ensure_loop()
    assert first is second, "a second loop would defeat the persistent client"
    client.close()
    assert sum(1 for event in events if event["event"] == "client.loop_started") == 1
    assert any(event["event"] == "client.closed" for event in events)


def test_try_send_reports_success_when_delivery_works() -> None:
    """The happy path returns True so callers can distinguish the two outcomes."""
    client = _client()
    client.send = lambda kind, payload: None  # type: ignore[method-assign]
    assert client.try_send("audit", {"records": []}) is True


def test_try_send_reports_failure_instead_of_raising() -> None:
    """Post-game the peer may be gone; that is reported, never raised."""
    events: list[dict] = []
    client = _client(events)
    try:
        assert client.try_send("audit", {"records": []}) is False
    finally:
        client.close()
    assert any(event["event"] == "client.send_failed" for event in events)
