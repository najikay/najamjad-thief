"""Our own guards must never cost us a game (T-2101 follow-up).

Found by the six-game rehearsal against the reference, at game 4: our inbound
guard rejected the opponent's legitimate turn with *"inbound rate limit of
120/min exceeded"*, and we then timed out waiting for the message we had thrown
away ourselves. Three mini-games had already gone by, so nothing shorter would
have caught it.

The mistake was an assumption, not an arithmetic slip: 120/min is 2 per second,
which is generous for human-paced turns and absurd for a game where a turn costs
milliseconds. This is the second time this project has throttled its own
protocol traffic — the first was the outbound gatekeeper at 30/min.

The tests below are about *volume*, not correctness of any single message.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.session_guard import DEFAULT_MAX_PER_MINUTE, SessionGuard
from najamjad_agent.shared.rate_limits import for_service, load_rate_limits

LIMITS = Path("config/rate_limits.json")
#: A mini-game is at most 35 turns each way; six of them plus audits and
#: per-game handshakes is the traffic of one real match.
MESSAGES_IN_A_FULL_MATCH = 6 * (35 * 2 + 4)


def turn(step: int) -> dict:
    """A minimally valid turn message."""
    return {"step": step, "sender": "them", "hint": "x", "smell_grid": {},
            "commit": f"{step:064d}"}


def test_the_inbound_ceiling_is_configured_not_hardcoded():
    """The last time this was a literal it silently forfeited a game."""
    configured = for_service(load_rate_limits(LIMITS), "inbound_peer")

    assert configured.requests_per_minute >= 1000, "must sit above anything honest play reaches"


def test_a_full_match_of_traffic_is_never_rate_limited():
    """The exact failure: a legitimate turn refused mid-series.

    All in one simulated minute — far faster than any real match — because the
    guard's window is a minute and the point is that volume alone cannot trip it.
    """
    guard = SessionGuard(clock=lambda: 0.0)

    refusals = [reason for reason in
                (guard.check({"sender": "them"}) for _ in range(MESSAGES_IN_A_FULL_MATCH))
                if reason]

    assert not refusals, f"our own guard refused honest play: {refusals[:1]}"


def test_a_genuine_flood_is_still_refused():
    """Raising the ceiling must not remove the backstop."""
    guard = SessionGuard(clock=lambda: 0.0, max_per_minute=10)

    for _ in range(10):
        assert guard.check({"sender": "them"}) is None
    refused = guard.check({"sender": "them"})

    assert refused and "rate limit" in refused


def test_the_ceiling_is_a_backstop_not_the_real_flood_protection():
    """The bounded queue is what actually stops a peer exhausting memory: it
    refuses politely and does not grow. The rate limit only has to be high
    enough never to bind on honest traffic."""
    inboxes = Inboxes(maxsize=4)

    accepted = [not inboxes.accept("turn", turn(step)).errors for step in range(1, 12)]

    assert sum(accepted) <= 4, "the queue bounds itself"
    assert inboxes.accept("turn", turn(99)).errors, "and says so rather than growing"


@pytest.mark.parametrize("kind", ["turn", "negotiate", "audit"])
def test_every_protocol_channel_survives_a_full_match(kind: str):
    """A per-game handshake and an audit exchange are protocol traffic too, and
    an opponent who re-negotiates each mini-game sends more of it than we do."""
    guard = SessionGuard(clock=lambda: 0.0)

    for _ in range(MESSAGES_IN_A_FULL_MATCH):
        assert guard.check({"sender": "them", "kind": kind}) is None


def test_the_shipped_default_matches_the_shipped_config():
    """A default that disagrees with the config is a trap for anyone who builds
    `Inboxes` directly — which the tests and the two-process harness both do."""
    configured = for_service(load_rate_limits(LIMITS), "inbound_peer").requests_per_minute

    assert configured == DEFAULT_MAX_PER_MINUTE


def test_the_note_records_why_the_ceiling_is_where_it_is():
    """This value looks arbitrary and is not; the reasoning has to survive."""
    services = json.loads(LIMITS.read_text(encoding="utf-8"))["rate_limits"]["services"]

    assert "flood" in services["inbound_peer"]["_note"].lower()
