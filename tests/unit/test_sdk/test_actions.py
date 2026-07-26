"""The action half of the SDK.

Delegation is easy to get wrong in a way tests with fakes never notice: a fake
happily answers `accept()` even though the real collaborator only has `agree()`.
Two of these methods shipped with exactly that bug, so the last test here checks
the delegations against the *real* classes rather than against stand-ins.
"""

import inspect

import pytest

from najamjad_agent.negotiation.flow import Negotiation
from najamjad_agent.net.mcp_server import PeerServer
from najamjad_agent.net.tunnel import Tunnel
from najamjad_agent.sdk.actions import AgentActions


class FakeServer:
    """A peer server that records what it was told to do."""

    def __init__(self, running: bool = False) -> None:
        self.url = "http://127.0.0.1:8802/mcp"
        self.running = running
        self.started = 0

    def start(self) -> None:
        self.started += 1
        self.running = True


class FakeTunnel:
    """A tunnel that records start/stop."""

    def __init__(self) -> None:
        self.public_url = "https://cop.4laboratory.com/mcp"
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def test_starting_the_peer_returns_the_address_peers_should_call():
    server, tunnel = FakeServer(), FakeTunnel()
    actions = AgentActions(server=server, tunnel=tunnel)

    url = actions.start_peer()

    assert url == "https://cop.4laboratory.com/mcp"
    assert (server.started, tunnel.started) == (1, 1)


def test_without_a_tunnel_the_local_url_is_returned():
    actions = AgentActions(server=FakeServer())

    assert actions.start_peer() == "http://127.0.0.1:8802/mcp"


def test_the_tunnel_can_be_skipped_for_local_play():
    tunnel = FakeTunnel()
    actions = AgentActions(server=FakeServer(), tunnel=tunnel)

    actions.start_peer(with_tunnel=False)

    assert tunnel.started == 0


def test_starting_without_a_server_fails_with_an_actionable_message():
    with pytest.raises(RuntimeError, match="load a config first"):
        AgentActions().start_peer()


def test_stopping_terminates_the_tunnel_process():
    """The tunnel outlives us if unstopped, pointing a public name at a dead port."""
    tunnel = FakeTunnel()

    AgentActions(server=FakeServer(), tunnel=tunnel).stop_peer()

    assert tunnel.stopped == 1


def test_stopping_with_nothing_running_is_safe():
    AgentActions().stop_peer()  # must not raise


def test_serving_reflects_the_server_state():
    server = FakeServer(running=True)

    assert AgentActions(server=server).serving is True
    assert AgentActions().serving is False


def test_preflight_reports_the_checks_it_was_given():
    actions = AgentActions(checks={"tunnel": lambda: "up", "gmail": lambda: 1 / 0})

    report = actions.preflight()

    assert report.ready is False
    assert [check.name for check in report.failures] == ["gmail"]


def test_archiving_bundles_the_workspace_and_emits(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "artifacts").mkdir(parents=True)
    (workspace / "artifacts" / "result.json").write_text("{}", encoding="utf-8")
    events: list[dict] = []
    actions = AgentActions(workspace=workspace, emit=events.append)

    report = actions.archive_match(tmp_path / "match.zip")

    assert report.included == ["artifacts/result.json"]
    assert events[0]["event"] == "match.archived"


def test_verifying_a_log_goes_through_the_replay_verifier(tmp_path):
    log = tmp_path / "log.json"
    log.write_text('{"records": [{"payload": {"step": 1}, "nonce": "a", "commit": "b"}]}', "utf-8")

    assert AgentActions().verify_log(log).passed is False


@pytest.mark.parametrize(
    ("method", "collaborator", "target"),
    [
        ("start_peer", PeerServer, "start"),
        ("stop_peer", Tunnel, "stop"),
        ("propose_terms", Negotiation, "propose"),
        ("approve_terms", Negotiation, "agree"),
    ],
)
def test_every_delegation_targets_a_method_that_really_exists(method, collaborator, target):
    """Fakes answer anything. `approve_terms` shipped calling `accept()` on a
    flow that only has `agree()`, and no fake-based test could have noticed."""
    assert hasattr(collaborator, target), f"{collaborator.__name__} has no {target}()"
    assert target in inspect.getsource(getattr(AgentActions, method))


def test_the_public_url_is_empty_before_anything_is_configured():
    assert AgentActions().public_url == ""


def test_archive_accepts_extra_sources(tmp_path):
    extra = tmp_path / "shots"
    extra.mkdir()
    (extra / "board.png").write_bytes(b"png")

    report = AgentActions(workspace=tmp_path / "ws").archive_match(
        tmp_path / "m.zip", extra={"screenshots": extra}
    )

    assert report.included == ["screenshots/board.png"]
    assert set(report.missing_sources) == {"artifacts", "events", "config"}


def test_approve_terms_passes_identity_through():
    class Flow:
        def __init__(self) -> None:
            self.seen: list[tuple] = []

        def agree(self, terms, identity=None):
            self.seen.append((terms, identity))
            return {"ok": True}

    flow = Flow()
    AgentActions(negotiation=flow).approve_terms({"board_size": 7}, {"group": "najamjad"})

    assert flow.seen == [({"board_size": 7}, {"group": "najamjad"})]


def test_propose_terms_delegates_to_the_flow():
    class Flow:
        def propose(self, terms=None):
            return {"proposed": terms}

    assert AgentActions(negotiation=Flow()).propose_terms({"x": 1}) == {"proposed": {"x": 1}}


def test_actions_hold_no_decision_logic():
    """Guidelines §5.3: a branch here is a decision that belongs in the domain."""
    source = inspect.getsource(AgentActions)

    assert source.count("    for ") == 0, "iteration is logic; delegate it"
    assert "while " not in source
