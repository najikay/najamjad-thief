"""Endpoint liveness (T-2421).

The panel's whole value is that an operator trusts it at 20:00. So the tests
are mostly about the three-way distinction it has to keep straight:

    reachable  — something accepted a connection
    silent     — configured, but nothing is listening  → this stops a match
    unasked    — not configured yet                    → this is just Tuesday

Collapsing the last two is the failure mode worth guarding: an empty
`opponent_url` painted red on every idle afternoon teaches the operator that
red means nothing, which is exactly when a real outage gets waved past.
"""

from najamjad_agent.net import liveness
from najamjad_agent.net.liveness import LISTENING, SILENT, UNCONFIGURED, UNPARSEABLE

UP = "http://127.0.0.1:8801/mcp"


def answering(monkeypatch, listening: bool) -> None:
    """Patch the readiness check the panel actually calls.

    This used to patch `is_listening`, the TCP probe. The panel now uses
    `is_ready`, which speaks HTTP to an `http(s)` target — because a tunnel
    edge accepts TCP whether or not the agent behind it is alive, so the panel
    reported an absent opponent as "answering" while the match wait, probing
    the same address, correctly recorded `opponent.absent`.
    """
    monkeypatch.setattr(liveness, "is_ready", lambda *_a, **_k: listening)


def test_an_answering_endpoint_is_green(monkeypatch):
    answering(monkeypatch, True)

    probe = liveness.check("our agent", UP)

    assert probe.reachable is True and probe.detail == LISTENING


def test_a_configured_endpoint_with_nothing_behind_it_is_red(monkeypatch):
    answering(monkeypatch, False)

    probe = liveness.check("opponent", UP)

    assert probe.reachable is False and probe.detail == SILENT


def test_an_unconfigured_endpoint_is_neither_green_nor_red():
    """`None`, not `False` — a match not yet scheduled is not a fault."""
    probe = liveness.check("opponent", "")

    assert probe.reachable is None and probe.detail == UNCONFIGURED


def test_a_malformed_url_is_a_fault_rather_than_a_blank():
    """A typo'd URL is configured-and-wrong, which the operator must see."""
    probe = liveness.check("opponent", "cop.4laboratory.com/mcp")

    assert probe.reachable is False and probe.detail == UNPARSEABLE


def test_probing_never_raises_on_a_dead_host():
    """The panel must survive what it is there to report on.

    A real connection to a closed local port, not a stubbed one: the point is
    that the transport error is handled, and mocking the probe here would
    test nothing.
    """
    assert liveness.check("dead", "http://127.0.0.1:59999").reachable is False


def test_the_survey_keeps_the_order_it_was_given(monkeypatch):
    """The panel reads top to bottom; a shuffling list is hard to scan."""
    answering(monkeypatch, True)

    names = [row["name"] for row in liveness.survey({"a": UP, "b": UP, "c": UP})]

    assert names == ["a", "b", "c"]


def test_only_configured_failures_block(monkeypatch):
    """The summary line: unconfigured must not count as broken."""
    answering(monkeypatch, False)

    probes = liveness.survey({"our agent": UP, "opponent": ""})

    assert liveness.blocking_issues(probes) == ["our agent"]


def test_nothing_blocks_when_everything_answers(monkeypatch):
    answering(monkeypatch, True)

    assert liveness.blocking_issues(liveness.survey({"our agent": UP})) == []


def test_the_dict_shape_is_what_the_dashboard_renders(monkeypatch):
    answering(monkeypatch, True)

    row = liveness.check("our agent", UP).as_dict()

    assert set(row) == {"name", "url", "reachable", "detail"}
