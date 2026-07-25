"""HTTP surface of the dashboard.

These endpoints exist for the first paint and for a page that joins mid-match;
live updates arrive over the socket. See `test_no_polling.py` for the test that
keeps it that way.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from najamjad_agent.sdk.sdk import AgentSdk
from najamjad_agent.ui.app import create_app
from najamjad_agent.ui.views import FALLBACK_PAGE


def test_the_index_serves_the_dashboard_shell(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "<title>NajAmjad agent</title>" in response.text


def test_the_index_degrades_to_a_message_when_assets_are_missing(client, monkeypatch):
    monkeypatch.setattr("najamjad_agent.ui.views.STATIC", Path("/nonexistent-assets"))

    assert client.get("/").text == FALLBACK_PAGE


def test_health_reports_readiness_and_viewer_count(client):
    body = client.get("/api/health").json()

    assert body == {"ok": True, "ready": True, "viewers": 0}


def test_health_is_honest_before_a_game_starts():
    with TestClient(create_app(AgentSdk())) as bare:
        assert bare.get("/api/health").json()["ready"] is False


def test_snapshot_returns_every_panel(client):
    body = client.get("/api/snapshot").json()

    assert set(body) == {
        "board", "turn", "transcript", "negotiation", "budget", "provider",
        "gatekeepers", "report",
    }
    assert body["board"]["available"] is True


def test_events_endpoint_honours_the_limit(client, sdk):
    history = [{"event": f"e{index}"} for index in range(20)]
    sdk._events = type("Bus", (), {"history": history})()

    body = client.get("/api/events?limit=5").json()

    assert len(body["events"]) == 5
    assert body["events"][-1]["event"] == "e19"


def test_events_endpoint_is_empty_without_a_bus(client):
    assert client.get("/api/events").json() == {"events": []}
