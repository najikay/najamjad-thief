"""The viewer as a served page: routes, navigation, and banner discipline.

The rule the last tests here defend is that the browser renders a verdict it did
not compute. Hashing in the client would be a second implementation of the same
SHA-256, and when the two disagreed nobody would know which to believe.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.replay.app import STATIC, create_replay_app
from najamjad_agent.replay.session import ReplaySession

GOLDENS = Path(__file__).resolve().parents[2] / "goldens" / "artifacts"
REFERENCE = GOLDENS / "log_segal-police-team-vs-segal-thief-team_g01.json"
TAMPERED = GOLDENS / "log_tampered_step7.json"


@pytest.fixture()
def client() -> TestClient:
    """A viewer opened on the reference sample log."""
    return TestClient(create_replay_app(REFERENCE))


def test_the_viewer_page_is_served(client):
    response = client.get("/replay")

    assert response.status_code == 200
    assert "Replay viewer" in response.text


def test_the_summary_endpoint_reports_verified_ok(client):
    summary = client.get("/api/replay/summary").json()

    assert summary["loaded"] is True
    assert summary["banner"] == "Verified OK"
    assert summary["verified"] == 19


def test_every_step_is_available_in_one_request(client):
    steps = client.get("/api/replay/steps").json()["steps"]

    assert len(steps) == 19
    assert steps[1]["move"] == "MOVE:S"


def test_steps_can_be_walked_one_at_a_time(client):
    first = client.get("/api/replay/step/0").json()
    second = client.get("/api/replay/step/1").json()

    assert first["available"] is True
    assert first["total"] == 19
    assert (first["step"], second["step"]) == (0, 1)


@pytest.mark.parametrize("index", [-1, 19, 500])
def test_a_step_outside_the_log_is_refused_with_its_range(client, index):
    body = client.get(f"/api/replay/step/{index}").json()

    assert body["available"] is False
    assert "outside 0..18" in body["error"]


def test_a_tampered_log_serves_the_red_banner_and_the_failing_step():
    with TestClient(create_replay_app(TAMPERED)) as viewer:
        summary = viewer.get("/api/replay/summary").json()

    assert summary["banner"] == "TAMPERED"
    assert summary["passed"] is False
    assert summary["void"] is True
    assert summary["failed"] == [7]


def test_a_viewer_with_no_log_says_so_instead_of_erroring():
    with TestClient(create_replay_app()) as empty:
        summary = empty.get("/api/replay/summary").json()
        step = empty.get("/api/replay/step/0").json()

    assert summary["loaded"] is False
    assert step["available"] is False


def test_a_different_log_can_be_opened_at_runtime(client):
    body = client.post("/api/replay/load", json={"path": str(TAMPERED)}).json()

    assert body["ok"] is True
    assert body["banner"] == "TAMPERED"


def test_opening_a_missing_file_reports_why_and_keeps_the_current_log(client):
    body = client.post("/api/replay/load", json={"path": "/nowhere/log.json"}).json()

    assert body["ok"] is False
    assert "cannot read" in body["error"]
    assert client.get("/api/replay/summary").json()["banner"] == "Verified OK"


def test_loading_without_a_path_is_refused(client):
    assert client.post("/api/replay/load", json={}).json() == {
        "ok": False, "error": "no path supplied"
    }


def test_the_page_falls_back_to_a_message_when_assets_are_missing(client, monkeypatch):
    monkeypatch.setattr("najamjad_agent.replay.app.STATIC", Path("/nonexistent-viewer"))

    assert "assets are missing" in client.get("/replay").text


def client_code() -> str:
    """The viewer script with `//` comments stripped.

    Comments explain *why* there is no hashing here and legitimately name
    SHA-256; scanning them would make the rule unstatable in its own file.
    """
    lines = (STATIC / "replay.js").read_text(encoding="utf-8").splitlines()
    return "\n".join(line.split("//")[0] for line in lines)


def test_the_client_never_computes_a_hash_of_its_own():
    """T-1910: the browser renders the verifier's verdict, it does not re-derive it."""
    source = client_code()

    for forbidden in ("sha256", "SHA-256", "crypto.subtle", "digest("):
        assert forbidden not in source


def test_the_comment_stripper_does_not_hide_real_code():
    """Otherwise the test above could pass by blinding itself."""
    assert "fetch('/api/replay/summary')" in client_code()
    assert "renderSummary" in client_code()


def test_the_banner_text_comes_from_the_server_not_the_page():
    source = client_code()

    assert "summary.banner" in source
    assert "'Verified OK'" not in source
    assert "'TAMPERED'" not in source


def test_a_session_reports_its_source_once_loaded():
    session = ReplaySession(REFERENCE)

    assert session.loaded is True
    assert session.summary()["source"].endswith("_g01.json")


def test_a_session_loaded_from_memory_says_so():
    session = ReplaySession({"records": [{"payload": {"step": 1}, "nonce": "a", "commit": "b"}]})

    assert session.summary()["source"] == "<in-memory>"
    assert session.result is not None
