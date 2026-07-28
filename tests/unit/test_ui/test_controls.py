"""Dashboard controls (T-1820, T-1821).

The most important assertion here is a *negative* one: there is no route that
plays a counted match. Serving and stopping are reversible and cost nothing;
playing is graded and cannot be undone, and `docs/RUNBOOK.md` is the interface
for it. A button that loses a match is worse than no button.

The rest is about not lying to the operator. Every control returns the state the
server now holds, so a page cannot paint "serving" over a server that failed to
bind.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.ui.app import ConnectionHub, create_app
from najamjad_agent.ui.controls import (
    ControlDeniedError,
    approve_terms,
    controls_enabled,
    negotiation_state,
    start_peer,
    stop_peer,
)

TERMS = {"board_size": 7, "num_games": 6}


class Actions:
    public_url = "https://cop.4laboratory.com/mcp"
    last_artifacts: dict[str, Any] = {}

    def __init__(self) -> None:
        self.started = self.stopped = 0
        self.approved: list[dict] = []

    def start_peer(self, with_tunnel=False, with_dashboard=False):
        self.started += 1
        return self.public_url

    def stop_peer(self):
        self.stopped += 1

    def approve_terms(self, terms, identity=None):
        self.approved.append(terms)
        return {"signed": True}

    def preflight(self):
        raise RuntimeError("no opponent configured")


class Sdk:
    def __init__(self, timeline=None) -> None:
        self.ready = True
        self.controls_enabled = False
        self.actions = Actions()
        self._timeline = timeline or []

    def negotiation_timeline(self):
        return list(self._timeline)

    def snapshot(self):
        return {"board": {}, "turn": {}, "transcript": [], "negotiation": [],
                "budget": {}, "provider": {}, "gatekeepers": [], "report": {}}

    def provider(self):
        return {}

    def budget(self):
        return {}

    def cockpit(self):
        from najamjad_agent.sdk.sdk import AgentSdk

        return AgentSdk.cockpit(self)  # type: ignore[arg-type]

    def recent_events(self, limit: int = 100):
        return []


@pytest.fixture
def enabled(monkeypatch):
    """Controls turned on, as an operator would for a match."""
    monkeypatch.setattr("najamjad_agent.ui.controls.controls_enabled", lambda *_a, **_k: True)


# ------------------------------------------------------------- the safety line


def test_there_is_no_route_that_plays_a_counted_match():
    """The assertion that matters most.

    Playing is graded and irreversible. If this ever becomes a button, it should
    be a deliberate decision with a confirmation, not something that appeared
    because it was convenient.
    """
    client = TestClient(create_app(Sdk(), ConnectionHub()))

    for route in ("/api/control/play", "/api/control/match", "/api/play"):
        assert client.post(route).status_code == 404, f"{route} should not exist"


def test_controls_are_disabled_unless_the_operator_enables_them():
    """A disabled-by-default write path is one fewer thing to reason about.

    The flag is read off the SDK rather than a config file: the UI package may
    reach the agent only through the facade (ADR-005), and the first version of
    `controls.py` imported `shared.app_config` directly. The boundary meta-test
    caught it, correctly.
    """
    disabled, enabled_sdk = Sdk(), Sdk()
    enabled_sdk.controls_enabled = True

    assert controls_enabled(disabled) is False
    assert controls_enabled(enabled_sdk) is True


def test_every_write_action_is_refused_while_disabled():
    sdk = Sdk()

    for call in (lambda: start_peer(sdk), lambda: stop_peer(sdk),
                 lambda: approve_terms(sdk, TERMS)):
        with pytest.raises(ControlDeniedError, match="controls are disabled"):
            call()


def test_a_disabled_control_answers_403_rather_than_failing_silently():
    client = TestClient(create_app(Sdk(), ConnectionHub()))

    response = client.post("/api/control/peer", json={"action": "start"})

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


# ------------------------------------------------------------- server-driven


def test_reading_the_control_state_needs_no_permission():
    """An operator must be able to see the state they are not allowed to change."""
    client = TestClient(create_app(Sdk(), ConnectionHub()))
    body = client.get("/api/control").json()

    assert set(body) == {"peer", "negotiation"}
    assert body["peer"]["controls_enabled"] is False


def test_starting_returns_the_state_the_server_now_holds(enabled):
    """Not a promise that it worked — the state itself."""
    sdk = Sdk()

    state = start_peer(sdk)

    assert sdk.actions.started == 1
    assert state["serving"] is True and state["public_url"]


def test_stopping_is_offered_because_it_is_reversible(enabled):
    """An unstopped tunnel points a public name at a dead port."""
    sdk = Sdk()

    stop_peer(sdk)

    assert sdk.actions.stopped == 1


@pytest.mark.parametrize("action", ["", "restart", "play"])
def test_an_unknown_peer_action_is_refused(action, enabled):
    client = TestClient(create_app(Sdk(), ConnectionHub()))

    assert client.post("/api/control/peer", json={"action": action}).status_code == 400


# ------------------------------------------------------- negotiation approval


def test_a_pending_proposal_is_surfaced_for_a_human():
    """FR-NEG-4: a person approves terms before they are signed."""
    sdk = Sdk(timeline=[{"action": "proposed", "terms": TERMS}])

    assert negotiation_state(sdk)["awaiting_approval"] is True


def test_a_locked_negotiation_is_not_awaiting_anyone():
    sdk = Sdk(timeline=[{"action": "proposed"}, {"action": "locked"}])

    assert negotiation_state(sdk)["awaiting_approval"] is False


def test_approving_signs_exactly_what_was_shown(enabled):
    """The terms come back from the page rather than off the server's draft: a
    draft that changed between rendering and clicking must not be signed by
    that click."""
    sdk = Sdk(timeline=[{"action": "proposed"}])

    approve_terms(sdk, TERMS)

    assert sdk.actions.approved == [TERMS]


def test_approving_nothing_is_refused(enabled):
    """An empty draft means the page had nothing to show a human."""
    with pytest.raises(ControlDeniedError, match="empty"):
        approve_terms(Sdk(), {})
