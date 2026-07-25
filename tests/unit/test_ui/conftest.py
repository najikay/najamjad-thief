"""Fixtures for the dashboard tests."""

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.constants import Phase, Role
from najamjad_agent.domain.fsm import GameStateMachine
from najamjad_agent.sdk.sdk import AgentSdk
from najamjad_agent.ui.app import ConnectionHub, create_app
from tests.fakes.orchestration import build_state


@pytest.fixture
def sdk() -> AgentSdk:
    """An SDK with one mini-game attached, as the dashboard would see it."""
    agent = AgentSdk()
    fsm = GameStateMachine(game_uid="ui-test")
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    agent.attach_game(build_state(Role.COP), fsm)
    agent.record_message("in", "I am near the park", provider="peer", step=1)
    return agent


@pytest.fixture
def hub() -> ConnectionHub:
    """A fresh connection hub the test can inspect."""
    return ConnectionHub()


@pytest.fixture
def client(sdk: AgentSdk, hub: ConnectionHub) -> TestClient:
    """A test client with startup/shutdown run, so the loop is bound."""
    with TestClient(create_app(sdk, hub)) as test_client:
        yield test_client
