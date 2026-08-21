"""A failed handshake retries the same sub-game — it never renumbers it (T-2447).

The defect, from a real match: when a sub-game failed we advanced the counter
while the opponent retried the same one. After two failures we were numbering
games 3 and 4 while they numbered the identical games 5 and 6 — and two reports
describing one match with different `sub_game_number`s are contradictory, which
rules 33-35 can void for both teams.

Worse, at this commit a `HandshakeError` propagated out of `play_series`
entirely: one failed agreement exchange killed the whole series, six games lost
to a tunnel blip that a single retry would have absorbed.

The resilience boundary is deliberate and must survive this fix: a dropped
*turn* still costs exactly one mini-game (the timeout path through the turn
loop), and a dead *handshake* — after bounded retries — costs that one
mini-game as a technical outcome, never the series.
"""

from typing import Any

from najamjad_agent.constants import EndReason, Move, Role
from najamjad_agent.domain.handshake_retry import BUSY_RETRIES
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.match_resolution import HANDSHAKE_REOFFERS
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker
from najamjad_agent.negotiation.handshake import HandshakeError
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING

#: Failures enough to bury one window outright: every attempt of every re-offer.
#: Derived rather than typed, because both budgets are tuned against a live
#: opponent's sequencing and a hardcoded 3 quietly became "recovers immediately"
#: the first time one of them moved.
DEAD = (BUSY_RETRIES + 1) * HANDSHAKE_REOFFERS


class QuietPeer:
    """Answers nothing, so each played mini-game resolves on the timeout path."""

    def reset(self, sub_game: int = 0) -> None: ...

    #: Real transports replace the outbound session before each sub-game's
    #: handshake, because the peer may have been a different process last game.
    def new_session(self) -> None: ...

    def finish_sub_game(self) -> None: ...

    def send_turn(self, message: dict[str, Any]) -> bool:
        return True

    def receive_turn(self, timeout: float) -> None:
        return None

    def send_audit(self, payload: Any) -> None: ...

    def receive_audit(self, timeout: float) -> None:
        return None


class FlakyHandshake:
    """Fails a scripted number of times before agreeing, like a tunnel blip."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self) -> dict:
        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            raise HandshakeError("opponent sent no terms within 0.1s")
        return {"identity": {"group_id": "them"}}


def _runner(handshake: Any, games: int = 2, events: list | None = None) -> MatchRunner:
    return MatchRunner(
        params=build_state(Role.COP).board.params,
        tracker=SeriesTracker(
            "us", "them", ScoreTable.from_config(SCORING), Role.COP, total_games=games
        ),
        transport=QuietPeer(),
        build_state=lambda _p, role, sub: build_state(role),
        build_brain=lambda _role, _state: ScriptedBrain([Move.STAY]),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        first_role=Role.COP,
        emit=events.append if events is not None else None,
        response_timeout=0.01,
        max_retries=1,
        audit_timeout=0.01,
        handshake=handshake,
        # The window budget is priced in minutes of real waiting, so a test that
        # let it sleep for real would take a quarter of an hour to fail.
        sleep=lambda _seconds: None,
    )


def test_a_transient_failure_retries_the_same_sub_game() -> None:
    """One blip, one retry, and the numbering never moves."""
    handshake = FlakyHandshake(failures=1)
    runner = _runner(handshake)

    runner.play_series()

    numbers = [game["sub_game"] for game in runner.games]
    assert numbers == [1, 2], "the failed attempt must not consume a number"
    assert handshake.calls == 3  # one failure, one retry, one clean game 2


def test_the_retry_is_announced() -> None:
    """A silent retry hides the tunnel problem the operator needs to hear about."""
    events: list[dict] = []
    _runner(FlakyHandshake(failures=1), events=events).play_series()

    assert any(event.get("event") == "handshake.waiting_for_window" for event in events)


def test_a_dead_handshake_costs_one_mini_game_never_the_series() -> None:
    """Bounded: exhaustion resolves that sub-game as a technical outcome.

    Before this fix the HandshakeError propagated out of `play_series` — six
    games lost to one dead agreement exchange.
    """
    events: list[dict] = []
    runner = _runner(FlakyHandshake(failures=DEAD * 2), games=2, events=events)

    result = runner.play_series()  # must not raise

    assert len(runner.games) == 2
    assert all(game["end_reason"] == EndReason.OPPONENT_QUIT.value for game in runner.games)
    # A technical loss zeroes both sides (book Table 2) — nobody profits.
    assert result.total_score == {"us": 0, "them": 0}
    assert any(event.get("event") == "handshake.exhausted" for event in events)


def test_recovery_after_exhaustion_is_still_possible() -> None:
    """Game 1 dies to a dead handshake; game 2 plays when the peer returns."""
    handshake = FlakyHandshake(failures=DEAD)  # exactly enough to bury game 1
    runner = _runner(handshake, games=2)

    runner.play_series()

    reasons = [game["end_reason"] for game in runner.games]
    assert reasons[0] == EndReason.OPPONENT_QUIT.value
    assert reasons[1] == EndReason.TIMEOUT.value  # played, quiet peer, normal path


def test_a_dropped_turn_still_costs_exactly_one_mini_game() -> None:
    """The existing resilience boundary, pinned so this fix cannot move it."""
    runner = _runner(handshake=None, games=2)

    runner.play_series()

    assert [game["end_reason"] for game in runner.games] == [
        EndReason.TIMEOUT.value,
        EndReason.TIMEOUT.value,
    ]


def test_a_busy_peer_does_not_spend_the_ordinary_retry_budget() -> None:
    """Skew must cost a short wait, not the attempts reserved for an outage.

    With `handshake_retries = 2` the ordinary budget is three attempts. A peer
    who started a few seconds early refuses every one of them in milliseconds,
    so the budget was gone long before their sub-game ended — which is exactly
    how a few seconds of drift became a lost series.
    """
    from najamjad_agent.domain.handshake_retry import BUSY_RETRIES, agree_on_terms
    from najamjad_agent.negotiation.handshake import HandshakeBusyError

    events: list[dict] = []
    calls = {"n": 0}
    waited: list[float] = []

    def busy_until_the_boundary() -> None:
        calls["n"] += 1
        if calls["n"] <= 4:
            raise HandshakeBusyError("a mini-game is in progress")

    agreed = agree_on_terms(
        busy_until_the_boundary, sub_game=1, retries=2,
        emit=events.append, sleep=waited.append,
    )

    assert agreed, "gave up on a peer that was merely finishing a mini-game"
    assert calls["n"] == 5
    assert len(waited) == 4, "a busy retry must pause, or it becomes a spin"
    assert all(event["event"] == "handshake.waiting_for_window" for event in events)
    assert BUSY_RETRIES >= 4


def test_an_unreachable_peer_still_exhausts_on_schedule() -> None:
    """The budget that matters for a real outage is unchanged: 1 + retries."""
    from najamjad_agent.domain.handshake_retry import agree_on_terms

    events: list[dict] = []

    def always_down() -> None:
        raise RuntimeError("connection refused")

    assert not agree_on_terms(
        always_down, sub_game=1, retries=2, emit=events.append, sleep=lambda _s: None
    )
    assert [event["event"] for event in events] == [
        "handshake.retry", "handshake.retry", "handshake.exhausted",
    ]


def test_a_terms_mismatch_is_not_waited_out_like_a_late_peer() -> None:
    """Sixteen minutes is the right budget for a window that has not opened and
    the wrong one for two peers holding different contracts.

    That never resolves by waiting — it resolves by one of us editing a config —
    so it falls to the ordinary budget and an operator hears about it in
    seconds. Pinned because the classification is by exception *type name*, and
    `TermsMismatchError` subclasses `HandshakeError`, which IS on the patient
    list: a future refactor that collapses the two would re-introduce the wait
    silently.
    """
    from najamjad_agent.domain.handshake_retry import agree_on_terms
    from najamjad_agent.negotiation.handshake import TermsMismatchError

    events: list[dict] = []
    waited: list[float] = []

    def disagrees() -> None:
        raise TermsMismatchError("the opponent signed different terms — max_moves")

    assert not agree_on_terms(disagrees, sub_game=1, retries=2,
                              emit=events.append, sleep=waited.append)
    assert [event["event"] for event in events] == [
        "handshake.retry", "handshake.retry", "handshake.exhausted",
    ]
    assert waited == [], "a disagreement is not a peer we are waiting for"
