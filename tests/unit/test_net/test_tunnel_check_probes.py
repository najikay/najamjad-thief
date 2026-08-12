"""The tunnel line must report what the hostname answered, not what we configured.

`tunnel_check` used to `return tunnel.public_url` — echoing back the configured
string — under a docstring claiming it confirmed a live endpoint, while
`docs/runbook-network.md` claimed preflight made a self-call through the public
URL. So the line printed `PASS` with nothing listening, which is the exact trap
that runbook warns about, dressed as reassurance.

Three states, three responses, and only one of them is a red line.
"""

from __future__ import annotations

from typing import Any

import pytest

from najamjad_agent.net import preflight_checks
from najamjad_agent.net.http_probe import ProbeResult

URL = "https://thief.4laboratory.com/mcp"


class _Tunnel:
    def __init__(self, url: str = URL) -> None:
        self.public_url = url


def _with_probe(monkeypatch: pytest.MonkeyPatch, result: ProbeResult) -> Any:
    """Pin what the public hostname answers, so no test needs the network."""
    monkeypatch.setattr(
        "najamjad_agent.net.http_probe.probe", lambda _url, **_k: result
    )
    return preflight_checks.tunnel_check(_Tunnel())


def test_an_answering_origin_is_the_only_state_that_passes_as_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """406 is healthy: a stateless MCP server refusing a bare GET is an answer."""
    probe = _with_probe(monkeypatch, ProbeResult(True, status=406, body="text/event-stream"))

    detail = probe()

    assert "answered" in detail
    assert "406" in detail
    assert URL in detail


def test_an_edge_failure_says_so_and_does_not_claim_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """502/530 before the agent is up is expected, so it must not block.

    Preflight is designed to run *before* the agent starts — `port_check` passes
    only while the port is still free — so failing here would make the tool
    contradict its own documented sequence. It must still refuse to call this
    proof.
    """
    probe = _with_probe(monkeypatch, ProbeResult(True, status=530, body="error 1033"))

    detail = probe()

    assert "NOT proof" in detail
    assert "530" in detail


def test_nothing_answering_at_all_is_a_red_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing DNS route is not fixed by starting the agent, so it blocks."""
    probe = _with_probe(monkeypatch, ProbeResult(False, error="no such host"))

    with pytest.raises(RuntimeError, match="could not be reached"):
        probe()


def test_local_play_is_still_not_applicable() -> None:
    """No tunnel configured is a legitimate setup, not a failure."""
    assert preflight_checks.tunnel_check(None)() is None
    assert preflight_checks.tunnel_check(_Tunnel(""))() is None


def test_the_check_never_echoes_the_configured_url_as_the_whole_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression itself: a bare hostname string is not a verdict."""
    probe = _with_probe(monkeypatch, ProbeResult(True, status=406))

    assert probe() != URL
