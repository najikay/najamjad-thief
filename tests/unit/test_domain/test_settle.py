"""Waiting for a peer to bury the mini-game we walked away from.

When we abandon mid-play the opponent does not know: they are still waiting on a
turn and will sit there until their own watchdog fires. Offering them the next
handshake before that happens is how one dead mini-game becomes two.

The constraint that shapes every test here is that this must cost **nothing** on
the healthy path. Five of six mini-games end cleanly, and a delay on those would
add minutes to every series to insure against something that did not happen.
"""

import pytest

from najamjad_agent.domain.settle import MAX_SETTLE_SECONDS, settle, settle_seconds


def test_a_clean_game_costs_nothing() -> None:
    """The design constraint. Most games end cleanly and must not be slowed."""
    assert settle_seconds(watchdog=60.0, abandoned=False) == 0.0


def test_an_abandoned_game_waits_the_agreed_watchdog() -> None:
    """Long enough for their watchdog to fire and close the game we left."""
    assert settle_seconds(watchdog=60.0, abandoned=True) == 60.0


def test_the_wait_is_capped_however_the_watchdog_is_configured() -> None:
    """Past the agreed 60 s the peer has certainly closed; more only burns clock."""
    assert settle_seconds(watchdog=600.0, abandoned=True) == MAX_SETTLE_SECONDS


def test_a_negative_or_zero_watchdog_disables_the_wait() -> None:
    """Zero is what every caller that has not opted in receives."""
    assert settle_seconds(watchdog=0.0, abandoned=True) == 0.0
    assert settle_seconds(watchdog=-5.0, abandoned=True) == 0.0


def test_nothing_is_slept_on_the_healthy_path() -> None:
    """Asserted on the injected clock, not on elapsed time — CI pays for sleeps."""
    slept: list[float] = []

    settle(60.0, abandoned=False, sleep=slept.append)

    assert slept == []


def test_the_wait_is_actually_spent_after_an_abandonment() -> None:
    slept: list[float] = []

    spent = settle(60.0, abandoned=True, sleep=slept.append)

    assert slept == [60.0]
    assert spent == 60.0


def test_the_wait_is_announced_rather_than_silent() -> None:
    """A silent minute is indistinguishable from a hang to whoever is watching."""
    events: list[dict] = []

    settle(60.0, abandoned=True, sleep=lambda _s: None, emit=events.append, sub_game=3)

    assert events[0]["event"] == "series.settling"
    assert events[0]["sub_game"] == 3
    assert events[0]["seconds"] == 60.0


def test_a_skipped_wait_announces_nothing() -> None:
    """No event on the healthy path, or the log fills with non-events."""
    events: list[dict] = []

    settle(60.0, abandoned=False, sleep=lambda _s: None, emit=events.append)

    assert events == []


@pytest.mark.parametrize("watchdog", [0.5, 30.0, 60.0])
def test_the_announced_duration_matches_the_one_slept(watchdog: float) -> None:
    """A log that disagrees with what happened is worse than no log."""
    slept: list[float] = []
    events: list[dict] = []

    settle(watchdog, abandoned=True, sleep=slept.append, emit=events.append)

    assert slept == [pytest.approx(events[0]["seconds"], abs=0.05)]
