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
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker
from najamjad_agent.negotiation.handshake import HandshakeError
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING


class QuietPeer:
    """Answers nothing, so each played mini-game resolves on the timeout path."""

    def reset(self) -> None: ...

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

    assert any(event.get("event") == "handshake.retry" for event in events)


def test_a_dead_handshake_costs_one_mini_game_never_the_series() -> None:
    """Bounded: exhaustion resolves that sub-game as a technical outcome.

    Before this fix the HandshakeError propagated out of `play_series` — six
    games lost to one dead agreement exchange.
    """
    events: list[dict] = []
    runner = _runner(FlakyHandshake(failures=99), games=2, events=events)

    result = runner.play_series()  # must not raise

    assert len(runner.games) == 2
    assert all(game["end_reason"] == EndReason.OPPONENT_QUIT.value for game in runner.games)
    # A technical loss zeroes both sides (book Table 2) — nobody profits.
    assert result.total_score == {"us": 0, "them": 0}
    assert any(event.get("event") == "handshake.exhausted" for event in events)


def test_recovery_after_exhaustion_is_still_possible() -> None:
    """Game 1 dies to a dead handshake; game 2 plays when the peer returns."""
    handshake = FlakyHandshake(failures=3)  # 1 + retries(2) exhausts game 1 exactly
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
