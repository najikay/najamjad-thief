"""Tests for the API gatekeeper: limiting, queueing, retries, backpressure."""

import pytest

from najamjad_agent.shared.gatekeeper import ApiGatekeeper, QueueFullError
from najamjad_agent.shared.rate_limits import RateLimitConfig


class FakeClock:
    """Manually advanced clock so limiter behaviour is deterministic."""

    def __init__(self) -> None:
        self.value = 0.0
        self.slept = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.value += seconds


def _gatekeeper(events: list[dict] | None = None, **overrides) -> tuple[ApiGatekeeper, FakeClock]:
    clock = FakeClock()
    config = RateLimitConfig(**{"requests_per_minute": 60, "concurrent_max": 2, **overrides})
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=config,
        emit=(events.append if events is not None else None),
        sleep=clock.sleep,
        clock=clock.now,
    )
    return keeper, clock


def test_a_normal_call_passes_straight_through() -> None:
    keeper, _ = _gatekeeper()
    assert keeper.execute(lambda value: value * 2, 21) == 42


def test_arguments_and_keywords_are_forwarded() -> None:
    keeper, _ = _gatekeeper()
    assert keeper.execute(lambda a, b=0: a + b, 1, b=2) == 3


def test_every_call_is_logged_for_monitoring() -> None:
    events: list[dict] = []
    keeper, _ = _gatekeeper(events)
    keeper.execute(lambda: "ok")
    assert any(event["event"] == "gatekeeper.call" for event in events)
    assert events[0]["service"] == "mcp_peer"


def test_burst_beyond_the_rate_waits_instead_of_failing() -> None:
    """Overflow queues (guidelines §5.3) — a move must never be dropped."""
    events: list[dict] = []
    keeper, clock = _gatekeeper(events, requests_per_minute=2)
    for _ in range(4):
        keeper.execute(lambda: "ok")
    assert clock.slept > 0, "the limiter throttled instead of rejecting"
    assert any(event["event"] == "gatekeeper.queued" for event in events)


def test_tokens_refill_over_time() -> None:
    keeper, clock = _gatekeeper(requests_per_minute=60)
    for _ in range(60):
        keeper.execute(lambda: "ok")
    clock.value += 60
    assert keeper.execute(lambda: "ok") == "ok"


def test_transient_failures_are_retried_then_succeed() -> None:
    events: list[dict] = []
    keeper, clock = _gatekeeper(events, max_retries=3, retry_after_seconds=5)
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("peer not ready")
        return "connected"

    assert keeper.execute(flaky) == "connected"
    assert attempts["count"] == 3
    assert clock.slept >= 10, "backoff was honoured between attempts"
    assert sum(1 for event in events if event["event"] == "gatekeeper.retry") == 2


def test_retries_are_bounded_and_then_raise() -> None:
    """An unbounded retry is indistinguishable from a hang."""
    events: list[dict] = []
    keeper, _ = _gatekeeper(events, max_retries=3)

    def always_fails() -> None:
        raise ConnectionError("peer is gone")

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        keeper.execute(always_fails)
    assert any(event["event"] == "gatekeeper.failed" for event in events)


def test_failure_preserves_the_original_cause() -> None:
    keeper, _ = _gatekeeper(max_retries=1)

    def always_fails() -> None:
        raise ValueError("root cause")

    with pytest.raises(RuntimeError) as caught:
        keeper.execute(always_fails)
    assert isinstance(caught.value.__cause__, ValueError)


def test_queue_depth_produces_backpressure_not_a_crash() -> None:
    events: list[dict] = []
    keeper, _ = _gatekeeper(events, queue_depth=100)
    keeper._waiting = 100  # simulate a saturated queue
    with pytest.raises(QueueFullError, match="queue depth"):
        keeper.execute(lambda: "ok")
    assert any(event["event"] == "gatekeeper.backpressure" for event in events)


def test_status_reports_load_for_the_dashboard() -> None:
    keeper, _ = _gatekeeper()
    keeper.execute(lambda: "ok")
    status = keeper.status()
    assert status.service == "mcp_peer"
    assert status.calls_made == 1
    assert status.in_flight == 0


def test_in_flight_is_released_even_when_the_call_fails() -> None:
    keeper, _ = _gatekeeper(max_retries=1)
    with pytest.raises(RuntimeError):
        keeper.execute(lambda: (_ for _ in ()).throw(OSError("boom")))
    assert keeper.status().in_flight == 0
