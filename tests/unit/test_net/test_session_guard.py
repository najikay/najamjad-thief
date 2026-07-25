"""Tests for session binding — keeping strangers out of a live match.

Our MCP endpoint is public and its URL is in our repository. Commit-reveal stops
the *opponent* rewriting history; nothing in the book stops a *third party*
injecting a turn. These tests cover that gap.
"""

import pytest

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.session_guard import SessionGuard, session_token

CONTRACT = "c" * 64
GAME_UID = "uid-2026-najamjad-vs-rival"
TURN = {"step": 1, "sender": "rival", "commit": "a" * 64, "hint": "north side"}


class StubMessage:
    def __init__(self, sender: str = "", token: str = "") -> None:
        self.sender = sender
        self.session_token = token


@pytest.fixture()
def events() -> list[dict]:
    return []


def _guard(events: list[dict], **kwargs) -> SessionGuard:
    return SessionGuard(emit=events.append, **kwargs)


def test_an_unbound_guard_admits_anyone_so_a_match_can_start(events: list[dict]) -> None:
    """Before negotiation a stranger is just a team saying hello."""
    guard = _guard(events)
    assert not guard.bound
    assert guard.check(StubMessage(sender="anyone")) is None


def test_binding_locks_the_match_to_one_opponent(events: list[dict]) -> None:
    guard = _guard(events)
    guard.bind("rival", CONTRACT, GAME_UID)
    assert guard.bound
    assert guard.check(StubMessage(sender="rival")) is None


def test_a_stranger_cannot_move_in_our_game(events: list[dict]) -> None:
    """The actual vulnerability: a well-formed turn from an outsider."""
    guard = _guard(events)
    guard.bind("rival")
    refusal = guard.check(StubMessage(sender="random-attacker"))
    assert refusal is not None
    assert "not the negotiated opponent" in refusal
    assert any(event["event"] == "session.rejected" for event in events)


def test_the_session_token_is_derived_not_transmitted() -> None:
    """Both peers compute it from the identical signed contract."""
    ours = session_token(CONTRACT, GAME_UID)
    theirs = session_token(CONTRACT, GAME_UID)
    assert ours == theirs
    assert len(ours) == 32


def test_a_different_contract_yields_a_different_token() -> None:
    assert session_token(CONTRACT, GAME_UID) != session_token("d" * 64, GAME_UID)


def test_a_different_game_yields_a_different_token() -> None:
    """A token from a finished match cannot be replayed into the next one."""
    assert session_token(CONTRACT, GAME_UID) != session_token(CONTRACT, "uid-other")


def test_a_forged_token_is_refused(events: list[dict]) -> None:
    guard = _guard(events)
    guard.bind("rival", CONTRACT, GAME_UID)
    refusal = guard.check(StubMessage(sender="rival", token="forged"))
    assert refusal is not None and "session token" in refusal


def test_the_correct_token_passes(events: list[dict]) -> None:
    guard = _guard(events)
    guard.bind("rival", CONTRACT, GAME_UID)
    good = session_token(CONTRACT, GAME_UID)
    assert guard.check(StubMessage(sender="rival", token=good)) is None


def test_a_peer_without_token_support_is_tolerated_but_noted(events: list[dict]) -> None:
    """Refusing reference-implementation opponents would cost us matches."""
    guard = _guard(events)
    guard.bind("rival", CONTRACT, GAME_UID)
    assert guard.check(StubMessage(sender="rival")) is None
    assert any(event["event"] == "session.unauthenticated" for event in events)


def test_a_flood_is_refused_before_it_reaches_the_game(events: list[dict]) -> None:
    guard = _guard(events, max_per_minute=10)
    guard.bind("rival")
    for _ in range(10):
        assert guard.check(StubMessage(sender="rival")) is None
    refusal = guard.check(StubMessage(sender="rival"))
    assert refusal is not None and "rate limit" in refusal
    assert any(event["event"] == "session.rate_limited" for event in events)


def test_the_rate_window_rolls_forward(events: list[dict]) -> None:
    clock = {"now": 0.0}
    guard = SessionGuard(max_per_minute=2, emit=events.append, clock=lambda: clock["now"])
    guard.bind("rival")
    assert guard.check(StubMessage(sender="rival")) is None
    assert guard.check(StubMessage(sender="rival")) is None
    assert guard.check(StubMessage(sender="rival")) is not None
    clock["now"] = 61.0
    assert guard.check(StubMessage(sender="rival")) is None


def test_releasing_allows_the_next_match(events: list[dict]) -> None:
    guard = _guard(events)
    guard.bind("rival")
    guard.release()
    assert not guard.bound
    assert guard.check(StubMessage(sender="a-new-team")) is None


def test_the_inbox_refuses_an_outsider_turn() -> None:
    """End to end: the guard sits in front of the queue, not beside it."""
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    inboxes.guard.bind("rival")
    result = inboxes.accept("turn", {**TURN, "sender": "attacker"})
    assert not result.ok
    assert inboxes.pending("turn") == 0
    assert any(event["event"] == "inbox.unauthorised" for event in events)


def test_an_outsider_cannot_advance_our_step_counter() -> None:
    """Identity is checked BEFORE sequence, or a stranger could desync us."""
    inboxes = Inboxes()
    inboxes.guard.bind("rival")
    inboxes.accept("turn", {**TURN, "step": 50, "sender": "attacker"})
    assert inboxes.accept("turn", {**TURN, "step": 1, "sender": "rival"}).ok


def test_the_negotiated_opponent_still_plays_normally() -> None:
    inboxes = Inboxes()
    inboxes.guard.bind("rival")
    assert inboxes.accept("turn", TURN).ok
    assert inboxes.pending("turn") == 1
