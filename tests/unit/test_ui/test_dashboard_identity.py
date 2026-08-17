"""Two processes, one port: the panel that showed the sibling's board (T-2709).

A split match runs a thief process and a cop process, and both dashboards
defaulted to 8000. uvicorn binds inside `Server.run()`, which we launch on a
daemon thread, so on a taken port it logged, called `sys.exit(1)`, and the
thread died alone: `start()` had already returned True with an empty `error`.
The losing terminal therefore behaved as though it were serving a dashboard,
and `http://127.0.0.1:8000/` answered from the *other* process.

What that cost us was an entire misdiagnosis. Watching one panel across a
series, the operator saw our piece at the corner [0,0] and concluded the thief
was starting there instead of at the agreed centre [3,3] — a bug in the game.
The engine was never wrong: all 156 archived mini-games start at the agreed
cell, and the panel was the cop's, labelled `police` in its own header, reached
through the thief terminal's URL. Before the split, one process meant one
truthful URL, which is why the earlier imreeyal series looked right.

So the fix is in two halves, and both are pinned here: a clash must be reported
(this file's first tests), and each process must be able to hold its own port
(the rest), because a panel per process is what makes the two boards
distinguishable in the first place.
"""

import socket

from najamjad_agent.sdk.actions import AgentActions
from najamjad_agent.sdk.sdk import AgentSdk
from najamjad_agent.shared.app_config import LOOPBACK, dashboard_bind, dashboard_override
from najamjad_agent.ui.app import ConnectionHub
from najamjad_agent.ui.server import DashboardServer


class DeadPanel:
    """A dashboard that refuses to start, honest about it — unlike a Mock."""

    def __init__(self) -> None:
        self.url = "http://127.0.0.1:8000/"
        self.error = "OSError: [Errno 98] address already in use"
        self.running = False

    def start(self) -> bool:
        return False


def sibling_holding_a_port() -> tuple[socket.socket, int]:
    """Stand in for the other match process: a real listener on a real port."""
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    held.bind((LOOPBACK, 0))
    held.listen(1)
    return held, held.getsockname()[1]


def test_a_port_the_sibling_holds_is_reported_not_swallowed() -> None:
    """The defect itself: `start()` used to return True with no error at all."""
    held, port = sibling_holding_a_port()
    try:
        server = DashboardServer(AgentSdk(), ConnectionHub(), port=port)

        started = server.start()

        assert started is False
        assert "address already in use" in server.error.lower()
        assert server.running is False
    finally:
        held.close()


def test_the_clash_is_detected_before_the_web_stack_is_even_built() -> None:
    """Claiming the port first is what makes the failure ours to report.

    `SO_REUSEADDR` is set, which permits a port left in TIME_WAIT by our own
    previous run; a *live* sibling is still refused, and that is the case the
    operator needs to hear about.
    """
    held, port = sibling_holding_a_port()
    try:
        server = DashboardServer(AgentSdk(), ConnectionHub(), port=port)
        assert server.start() is False
        assert server._thread is None  # never got as far as launching one
    finally:
        held.close()


def test_a_refused_panel_is_published_so_it_is_in_the_event_log() -> None:
    """Silence here is what let the wrong board be read for six sub-games."""
    seen: list[dict] = []

    url = AgentActions(dashboard=DeadPanel(), emit=seen.append).start_dashboard()

    assert url == ""
    assert [event for event in seen if event["event"] == "dashboard.unavailable"]
    assert "address already in use" in seen[0]["reason"]


def test_a_dead_panel_reports_no_url_so_the_cli_cannot_claim_to_serve_one() -> None:
    """`match` held a terminal open for a panel the sibling was serving."""
    assert AgentActions(dashboard=DeadPanel()).dashboard_url == ""
    assert AgentActions().dashboard_url == ""


def test_a_bare_port_moves_the_second_process_off_the_first_ones_port() -> None:
    """The operational fix: `--dashboard-host :8010` on the second terminal."""
    assert dashboard_override(":8010", dashboard_bind({})) == (LOOPBACK, 8010)


def test_a_host_and_port_are_both_honoured() -> None:
    assert dashboard_override("0.0.0.0:8010", (LOOPBACK, 8000)) == ("0.0.0.0", 8010)


def test_a_bare_host_still_means_what_it_always_meant() -> None:
    """The flag predates the port and its existing uses must not change."""
    assert dashboard_override("0.0.0.0", (LOOPBACK, 8000)) == ("0.0.0.0", 8000)


def test_nothing_supplied_leaves_the_configured_bind_alone() -> None:
    """And the configured bind stays loopback, which rules 8-9 require."""
    assert dashboard_override("", dashboard_bind({})) == (LOOPBACK, 8000)
    assert dashboard_override("   ", (LOOPBACK, 8000)) == (LOOPBACK, 8000)


def test_an_ipv6_literal_is_a_host_and_not_a_host_with_a_port() -> None:
    """`::1` is in `LOOPBACK_HOSTS`, so splitting on any colon would break it."""
    assert dashboard_override("::1", (LOOPBACK, 8000)) == ("::1", 8000)
