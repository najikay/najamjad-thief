"""Tests for who-failed attribution.

The operating requirement is symmetry: this must be as willing to say *we*
failed as to say *they* did, and as willing to say it does not know. A module
that concluded "them" whenever it was unsure would be worth less than nothing
in a rules 33-35 dispute — the first time it overreached, every other finding
it had ever made would be discounted with it.
"""

from najamjad_agent.net.fault_attribution import (
    INDETERMINATE,
    OPPONENT,
    OURS,
    attribute,
)
from najamjad_agent.net.http_probe import ProbeResult

OURS_URL = "https://cop.4laboratory.com/mcp"
THEIRS = "https://d664-176-229-170-175.ngrok-free.app/mcp"


def probe(**reachable):
    """A stand-in for the TCP probe, so tests need no network."""
    return lambda url: reachable.get(url, False)


def http(status=None, body="", reached=True):
    """A stand-in for the HTTP probe.

    Required, not optional: without it these tests reach the real internet and
    their verdict depends on whether an opponent's tunnel is up today.
    """
    return lambda url: ProbeResult(reached, status=status, body=body)


def test_our_tunnel_up_and_theirs_down_is_their_fault() -> None:
    """The case the whole module exists for: our egress demonstrably worked."""
    verdict = attribute(OURS_URL, THEIRS, "All connection attempts failed",
                        probe=probe(**{OURS_URL: True, THEIRS: False}))

    assert verdict.verdict == OPPONENT
    assert verdict.evidence["our_tcp"] is True
    assert verdict.evidence["their_tcp"] is False


def test_neither_endpoint_answering_is_our_fault() -> None:
    """Our network is then the common factor, and we say so."""
    verdict = attribute(OURS_URL, THEIRS, "All connection attempts failed",
                        probe=probe(**{OURS_URL: False, THEIRS: False}))

    assert verdict.verdict == OURS
    assert "common factor" in verdict.detail


def test_a_reachable_opponent_is_never_blamed_for_connectivity() -> None:
    """If their edge answers, whatever failed was not the connection."""
    verdict = attribute(OURS_URL, THEIRS, "some protocol error",
                        probe=probe(**{OURS_URL: True, THEIRS: True}),
                        http=http(reached=False))

    assert verdict.verdict == INDETERMINATE


def test_we_do_not_blame_them_when_we_cannot_show_our_own_health() -> None:
    """Without our own URL the comparison is not available, so neither is a verdict."""
    verdict = attribute("", THEIRS, "All connection attempts failed",
                        probe=probe(**{THEIRS: False}))

    assert verdict.verdict == INDETERMINATE
    assert "cannot compare" in verdict.detail


def test_an_unconfigured_opponent_yields_no_verdict() -> None:
    assert attribute(OURS_URL, "", "boom", probe=probe()).verdict == INDETERMINATE


def test_the_error_message_is_carried_as_evidence() -> None:
    """A verdict without the underlying fault is an assertion, not evidence."""
    verdict = attribute(OURS_URL, THEIRS, "Client failed to connect: nope",
                        probe=probe(**{OURS_URL: True, THEIRS: False}))

    assert "Client failed to connect" in verdict.evidence["error"]


def test_a_malformed_url_does_not_crash_the_probe() -> None:
    """This runs inside an already-failing turn; it must never be the thing that dies."""
    assert attribute(OURS_URL, "not a url", "boom", probe=probe()).verdict in {
        OPPONENT, OURS, INDETERMINATE
    }


def test_the_verdict_serialises_for_the_record() -> None:
    payload = attribute(OURS_URL, THEIRS, "x", probe=probe(**{OURS_URL: True})).as_dict()

    assert set(payload) == {"verdict", "detail", "evidence"}


def test_a_tunnel_edge_error_page_names_the_far_side() -> None:
    """The edge answering *for* an absent origin is the far side's own report.

    This is what a TCP probe could never see: the handshake completes, TLS
    completes, and the provider then says there is nothing behind it.
    """
    verdict = attribute(
        OURS_URL, THEIRS, "Client failed to connect: ",
        probe=probe(**{OURS_URL: True, THEIRS: True}),
        http=http(status=502, body="ERR_NGROK_3200: tunnel not found"),
    )

    assert verdict.verdict == OPPONENT
    assert verdict.evidence["their_http"]["edge_failure"] is True


def test_a_healthy_origin_makes_the_fault_ours_and_we_say_so() -> None:
    """The branch that matters most: it must be able to blame us.

    A stateless MCP server answers a bare GET with 405. If they answer us while
    our own client cannot connect, the client is the problem and no amount of
    evidence-gathering should be able to phrase that as their fault.
    """
    verdict = attribute(
        OURS_URL, THEIRS, "Client failed to connect: ",
        probe=probe(**{OURS_URL: True, THEIRS: True}),
        http=http(status=405),
    )

    assert verdict.verdict == OURS
    assert "the fault is on our side" in verdict.detail
