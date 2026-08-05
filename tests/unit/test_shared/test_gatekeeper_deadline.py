"""The retry budget was never the retry count — it was always the clock.

`config/rate_limits.json` allows `mcp_peer` ten attempts five seconds apart and
called that "about 45 s of persistence". It was not. Each attempt carries its
own 30 s call timeout and `PeerSession` reconnects once inside that, so one
message could occupy **645 s** against an agreed 60 s watchdog — and the time is
not idle, because our turn loop is blocked in that send, so the minutes come
straight out of the mini-games that follow.

Counting attempts cannot fix this: how long an attempt takes is not the
gatekeeper's to know. Only wall clock is.
"""

import pytest

from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig


class Clock:
    """A clock the test advances, so no test ever really waits."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _gatekeeper(clock: Clock, events: list[dict], **overrides):
    config = RateLimitConfig(
        requests_per_minute=6000, max_retries=10, retry_after_seconds=5, **overrides
    )
    return ApiGatekeeper("mcp_peer", config, sleep=clock.sleep, clock=clock,
                         emit=events.append)


def _always_fails(clock: Clock, cost: float):
    """A call that burns `cost` seconds and then fails, like a stalled peer."""

    def call() -> None:
        clock.now += cost
        raise RuntimeError("Client failed to connect: ")

    return call


def test_ten_retries_of_a_slow_call_run_far_past_the_watchdog() -> None:
    """The defect, measured. Without a deadline the ceiling is nonsense.

    30 s per attempt is the configured call timeout, and it is the *optimistic*
    figure — a session that reconnects once pays it twice.
    """
    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events)

    with pytest.raises(RuntimeError):
        keeper.execute(_always_fails(clock, cost=30.0))

    assert clock.now == pytest.approx(345.0)
    assert clock.now > 60.0, "the agreed watchdog is 60 s"


def test_the_deadline_stops_us_once_nobody_is_still_waiting() -> None:
    """345 s becomes 65 s. Note what that is *not*: a promise of under 60.

    The budget governs whether a **new** attempt may start, and cannot reach
    into one already in flight — so the true worst case is the deadline plus
    one response timeout, and Table 19 fixes that timeout at 30 s. For two or
    more attempts, no legal configuration can stay under a 60 s watchdog; the
    win is that the overrun is now bounded and small instead of unbounded.

    This is exactly why `MatchRunner`'s freeze threshold is a multiple of the
    agreed watchdog rather than equal to it.
    """
    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events, deadline_seconds=45)

    with pytest.raises(RuntimeError):
        keeper.execute(_always_fails(clock, cost=30.0))

    assert clock.now == pytest.approx(65.0)
    assert clock.now <= 45 + 30, "the deadline, plus at most one in-flight attempt"
    assert any(event["event"] == "gatekeeper.deadline" for event in events)


def test_a_fast_failure_keeps_almost_all_its_retries() -> None:
    """The deadline must not become a retry cut for the case it was not for.

    A peer that refuses instantly costs only the back-off, so nearly every
    attempt still fits inside the budget — which matters, because a flapping
    tunnel is exactly what the generous retry count was chosen for.
    """
    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events, deadline_seconds=45)

    with pytest.raises(RuntimeError):
        keeper.execute(_always_fails(clock, cost=0.0))

    # Nine, not ten: the tenth would *begin* at exactly 45 s, and a request
    # started at the deadline cannot land inside it. Losing that one costs
    # nothing — 40 s of persistence against a peer whose edge is flapping is
    # the behaviour the generous retry count was chosen for, and it survives.
    retries = [event for event in events if event["event"] == "gatekeeper.retry"]
    assert len(retries) == 9
    assert clock.now == pytest.approx(40.0)


def test_a_call_that_succeeds_is_never_deadlined() -> None:
    """The budget bounds failure, not work."""
    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events, deadline_seconds=45)

    def slow_but_fine() -> str:
        clock.now += 120.0
        return "ok"

    assert keeper.execute(slow_but_fine) == "ok"
    assert not [event for event in events if event["event"] == "gatekeeper.deadline"]


def test_the_deadline_is_off_by_default() -> None:
    """Every other service keeps exactly the behaviour it had.

    A deadline only makes sense where something on the far side has already
    stopped waiting for us. Gmail has not.
    """
    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events)

    with pytest.raises(RuntimeError):
        keeper.execute(_always_fails(clock, cost=30.0))

    assert not [event for event in events if event["event"] == "gatekeeper.deadline"]


def test_the_backoff_floor_is_untouched() -> None:
    """The legality argument, as an assertion rather than a comment.

    Appendix F Table 19 binds the *interval* between attempts at a 5 s minimum.
    Capping the total is a different quantity and makes us stricter; shortening
    the interval would breach the table, which is why an earlier fast-first
    backoff was abandoned rather than shipped.
    """
    from najamjad_agent.shared.rate_limits import MIN_RETRY_BACKOFF_SEC

    clock, events = Clock(), []
    keeper = _gatekeeper(clock, events, deadline_seconds=45)

    with pytest.raises(RuntimeError):
        keeper.execute(_always_fails(clock, cost=0.0))

    assert keeper.config.retry_after_seconds >= MIN_RETRY_BACKOFF_SEC


def test_a_deadline_under_one_backoff_refuses_to_load() -> None:
    """It would forbid the first retry — not a stricter policy, a broken one."""
    with pytest.raises(ValueError, match="no retry could ever run"):
        RateLimitConfig(retry_after_seconds=5, deadline_seconds=3).validate("mcp_peer")


def test_the_shipped_config_bounds_the_peer_below_the_watchdog() -> None:
    """The number that matters is the one in the file, not in a fixture."""
    from pathlib import Path

    from najamjad_agent.shared.rate_limits import for_service, load_rate_limits

    limits = load_rate_limits(Path("config/rate_limits.json"))
    peer = for_service(limits, "mcp_peer")

    assert peer.deadline_seconds == 45
    assert peer.deadline_seconds < 60, "the agreed watchdog_timeout_sec"
