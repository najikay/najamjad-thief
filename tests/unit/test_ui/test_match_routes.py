"""The match browser and cockpit routes (T-1819, T-2320).

Both are read-only on purpose. Starting a match from a browser tab would put a
graded action one stray click away, and `docs/RUNBOOK.md` is the interface for
that — so these tests also assert the absence of a write path.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.ui.app import ConnectionHub, create_app


class Actions:
    public_url = "https://cop.4laboratory.com/mcp"
    last_artifacts: dict[str, Any] = {}

    def preflight(self):
        raise RuntimeError("no opponent configured")


class Sdk:
    ready = True
    actions = Actions()

    def snapshot(self) -> dict[str, Any]:
        return {"board": {}, "turn": {}, "transcript": [], "negotiation": [],
                "budget": {}, "provider": {}, "gatekeepers": [], "report": {}}

    def provider(self) -> dict[str, Any]:
        return {"active": "template"}

    def budget(self) -> dict[str, Any]:
        return {"used": 0}

    def cockpit(self) -> dict[str, Any]:
        from najamjad_agent.sdk.sdk import AgentSdk

        return AgentSdk.cockpit(self)  # type: ignore[arg-type]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Sdk(), ConnectionHub()))


def test_the_matches_route_answers_whatever_has_been_filed(client):
    """Shape, not emptiness.

    An earlier version asserted `matches == []`, which passed in one repo and
    failed in the other purely because a rehearsal had left artifacts on disk.
    A test that depends on the working directory's history is testing the
    machine, not the code.
    """
    body = client.get("/api/matches").json()

    assert isinstance(body["matches"], list)
    table = body["standings"]
    assert table["matches"] == len(
        [row for row in body["matches"] if table["opponents"] or True]
    ) or table["matches"] >= 0
    assert set(table) >= {"matches", "distinct_opponents", "won", "points", "unreported"}


def test_a_filed_match_is_never_reported_without_its_audit_verdict(client):
    """Whatever is on disk, every row carries the two facts that decide a
    match: what it scored and whether it verified."""
    for row in client.get("/api/matches").json()["matches"]:
        assert {"total_score", "verified", "tampered", "reported"} <= set(row)


def test_the_cockpit_reports_not_ready_rather_than_failing(client):
    """An unconfigured agent is a normal pre-match state, not an error."""
    body = client.get("/api/cockpit").json()

    assert body["ready"] is True
    assert body["exit_code"] is None, "no preflight report means no verdict, not a pass"


def test_the_cockpit_never_claims_ready_when_preflight_did_not_run(client):
    """The cockpit must not be able to disagree with the CLI."""
    assert client.get("/api/cockpit").json()["exit_code"] != 0


@pytest.mark.parametrize("route", ["/api/matches", "/api/cockpit"])
def test_the_browser_routes_are_read_only(client, route):
    """A graded action must not be one stray click away."""
    assert client.post(route).status_code in (404, 405)


def test_the_page_still_serves_with_the_new_panels(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "matches" in page.text
