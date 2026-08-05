"""Rule 7 must exist at runtime, and must not fire on a healthy slow turn.

`net/watchdog.py` was correct, documented and unit-tested, and nothing in
`src/` ever constructed it — so the freeze protection rule 7 requires has never
run in a match. These tests cover the caller: that it exists, that it beats,
and above all that its threshold is far enough above a legal slow turn to be a
safety device rather than a new way to lose a game.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.freeze_guard import FREEZE_MULTIPLE, watching
from tests.fakes.orchestration import build_state


@pytest.fixture()
def state():
    return build_state(Role.COP)


def test_a_zero_watchdog_arms_nothing(state) -> None:
    """Disabled must mean disabled — every existing caller passes zero."""
    with watching(0.0, state, sub_game=1, emit=lambda _event: None) as beat:
        assert beat is None


def test_an_armed_guard_hands_back_a_heartbeat(state) -> None:
    """The turn loop calls this each half-turn; without it nothing beats."""
    with watching(60.0, state, sub_game=1, emit=lambda _event: None) as beat:
        assert beat is not None
        beat()


def test_the_thread_is_stopped_even_when_the_game_raises(state) -> None:
    """A leaked daemon thread per mini-game is six per series.

    The context manager exists for this: the turn loop can end by exception,
    and a `try/finally` a caller must remember is one it can forget.
    """
    import threading

    before = threading.active_count()
    with pytest.raises(ValueError, match="boom"), watching(
        60.0, state, sub_game=1, emit=lambda _event: None
    ):
        raise ValueError("boom")

    assert threading.active_count() <= before


def test_the_threshold_clears_a_legal_slow_turn(state) -> None:
    """The number that decides whether this helps or hurts.

    A single send may legally spend the gatekeeper's whole 45 s budget and then
    sit in the final attempt's 30 s response timeout, which Table 19 fixes — so
    75 s of silence is *healthy*, and a turn makes more than one send. At a
    threshold of one agreed watchdog this would fire on a slow but perfectly
    fine turn and throw the game away.
    """
    agreed, worst_legal_send = 60.0, 45 + 30

    assert agreed * FREEZE_MULTIPLE > worst_legal_send * 2


def test_it_records_rather_than_kills(state) -> None:
    """Rescue must not forfeit the mini-games that were still playable.

    Rule 35 scores a missing report as not having played, so a series that
    files six results beats one that files two and a stack trace. `Watchdog`
    accepts a shutdown callback because another caller might want one; ours
    deliberately does nothing, and the assertion is that firing completes
    cleanly and leaves execution to continue.
    """
    from najamjad_agent.net.watchdog import Watchdog

    events: list[dict] = []
    clock = iter([0.0, 1000.0])
    guard = Watchdog(
        threshold_seconds=1.0,
        persist_state=lambda: None,
        controlled_shutdown=lambda: None,
        clock=lambda: next(clock, 1000.0),
        emit=events.append,
    )

    assert guard.check()
    names = [event["event"] for event in events]
    assert "watchdog.shutdown" in names, "the rescue path did not complete"
    assert "watchdog.shutdown_failed" not in names
    assert guard.fired


def test_a_fired_watchdog_persists_the_live_state(state) -> None:
    """The point of firing: the mini-game stays auditable.

    Driven through `Watchdog` directly with a threshold already exceeded,
    because waiting three real watchdogs in a unit test is not a test.
    """
    from najamjad_agent.net.watchdog import Watchdog

    events: list[dict] = []
    clock = iter([0.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    guard = Watchdog(
        threshold_seconds=1.0,
        persist_state=lambda: events.append({"event": "watchdog.snapshot",
                                             "state": state.snapshot()}),
        controlled_shutdown=lambda: None,
        clock=lambda: next(clock, 1000.0),
        emit=events.append,
    )

    assert guard.check()
    names = [event["event"] for event in events]
    assert "watchdog.fired" in names
    assert "watchdog.snapshot" in names
    snapshot = next(e for e in events if e["event"] == "watchdog.snapshot")["state"]
    assert snapshot["step"] == state.step
