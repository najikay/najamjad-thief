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

OURS_URL = "https://cop.4laboratory.com/mcp"
THEIRS = "https://d664-176-229-170-175.ngrok-free.app/mcp"


def probe(**reachable):
    """A stand-in for the TCP probe, so tests need no network."""
    return lambda url: reachable.get(url, False)


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
                        probe=probe(**{OURS_URL: True, THEIRS: True}))

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
