"""Serving the dashboard beside a live match.

The single rule: a dashboard that cannot start must not stop the game. Losing
the window costs visibility, losing the match costs the league position — so
every failure here is caught, reported, and stepped over.
"""

from unittest import mock

from najamjad_agent.sdk.sdk import AgentSdk
from najamjad_agent.ui.app import ConnectionHub
from najamjad_agent.ui.server import DashboardServer


def build(port: int = 8123) -> DashboardServer:
    return DashboardServer(AgentSdk(), ConnectionHub(), port=port)


def test_the_url_points_where_an_operator_should_look():
    assert build(port=9000).url == "http://127.0.0.1:9000/"


def test_it_is_not_running_before_it_starts():
    assert build().running is False


def test_starting_launches_a_daemon_thread():
    server = build()

    with mock.patch("uvicorn.Server") as runner:
        runner.return_value.run = lambda: None
        assert server.start() is True

    assert server.error == ""


def test_starting_twice_does_not_start_twice():
    server = build()
    server._thread = mock.Mock(is_alive=mock.Mock(return_value=True))

    with mock.patch("uvicorn.Server") as runner:
        assert server.start() is True

    assert not runner.called


def test_a_failure_to_start_is_reported_and_survivable():
    """The whole point: the match continues without a dashboard."""
    server = build()

    with mock.patch("uvicorn.Config", side_effect=RuntimeError("port taken")):
        started = server.start()

    assert started is False
    assert "port taken" in server.error
    assert server.running is False


def test_a_missing_web_stack_is_survivable():
    server = build()

    with mock.patch.dict("sys.modules", {"uvicorn": None}):
        assert server.start() is False

    assert server.error


def test_the_actions_layer_reports_an_empty_url_when_it_could_not_start():
    from najamjad_agent.sdk.actions import AgentActions

    failing = mock.Mock(start=mock.Mock(return_value=False), url="http://127.0.0.1:8000/")

    assert AgentActions(dashboard=failing).start_dashboard() == ""


def test_the_actions_layer_returns_the_url_on_success():
    from najamjad_agent.sdk.actions import AgentActions

    ok = mock.Mock(start=mock.Mock(return_value=True), url="http://127.0.0.1:8000/")

    assert AgentActions(dashboard=ok).start_dashboard() == "http://127.0.0.1:8000/"


def test_a_dead_dashboard_does_not_stop_the_peer_coming_online():
    from najamjad_agent.sdk.actions import AgentActions

    server = mock.Mock(url="http://127.0.0.1:8802/mcp", running=False)
    failing = mock.Mock(start=mock.Mock(return_value=False))

    url = AgentActions(server=server, dashboard=failing).start_peer(with_tunnel=False)

    assert url == "http://127.0.0.1:8802/mcp"
    assert server.start.called
