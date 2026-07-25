"""Tests for the watchdog: freeze detection, state rescue, controlled shutdown."""

import pytest

from najamjad_agent.net.watchdog import Watchdog


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _watchdog(threshold: float = 60.0, events: list[dict] | None = None, **kwargs):
    clock = ManualClock()
    calls: dict[str, int] = {"persist": 0, "shutdown": 0}

    def persist():
        calls["persist"] += 1
        return {"state": "saved"}

    def shutdown():
        calls["shutdown"] += 1

    dog = Watchdog(
        threshold_seconds=threshold,
        persist_state=kwargs.get("persist_state", persist),
        controlled_shutdown=kwargs.get("controlled_shutdown", shutdown),
        clock=clock.now,
        emit=(events.append if events is not None else None),
    )
    return dog, clock, calls


def test_threshold_comes_from_configuration() -> None:
    """Appendix F Table 19 default is 60 s and negotiable — never hardcoded."""
    dog, _, _ = _watchdog(threshold=90.0)
    assert dog.threshold == 90.0


def test_non_positive_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        Watchdog(0, lambda: None, lambda: None)


def test_a_healthy_loop_never_fires() -> None:
    dog, clock, calls = _watchdog(threshold=60)
    for _ in range(10):
        clock.advance(30)
        dog.beat()
        assert not dog.check()
    assert calls == {"persist": 0, "shutdown": 0}


def test_silence_beyond_the_threshold_fires_the_rescue() -> None:
    dog, clock, calls = _watchdog(threshold=60)
    clock.advance(61)
    assert dog.check()
    assert calls == {"persist": 1, "shutdown": 1}
    assert dog.fired


def test_state_is_persisted_before_shutdown() -> None:
    """Order matters: a shutdown that loses the audit trail is a forfeit."""
    order: list[str] = []
    dog, clock, _ = _watchdog(
        threshold=10,
        persist_state=lambda: order.append("persist"),
        controlled_shutdown=lambda: order.append("shutdown"),
    )
    clock.advance(11)
    dog.check()
    assert order == ["persist", "shutdown"]


def test_firing_is_idempotent() -> None:
    dog, clock, calls = _watchdog(threshold=10)
    clock.advance(11)
    assert dog.check()
    assert not dog.check(), "a second check must not rescue twice"
    assert calls["persist"] == 1


def test_a_failing_persist_still_attempts_shutdown() -> None:
    """We would rather lose the snapshot than leave a zombie holding a tunnel."""
    events: list[dict] = []
    shutdowns: list[str] = []

    def bad_persist():
        raise OSError("disk full")

    dog, clock, _ = _watchdog(
        threshold=5,
        events=events,
        persist_state=bad_persist,
        controlled_shutdown=lambda: shutdowns.append("done"),
    )
    clock.advance(6)
    dog.check()
    assert shutdowns == ["done"]
    assert any(event["event"] == "watchdog.persist_failed" for event in events)


def test_a_failing_shutdown_is_reported() -> None:
    events: list[dict] = []

    def bad_shutdown():
        raise RuntimeError("cannot stop")

    dog, clock, _ = _watchdog(threshold=5, events=events, controlled_shutdown=bad_shutdown)
    clock.advance(6)
    dog.check()
    assert any(event["event"] == "watchdog.shutdown_failed" for event in events)


def test_beats_reset_the_silence_measure() -> None:
    dog, clock, _ = _watchdog(threshold=60)
    clock.advance(59)
    dog.beat()
    clock.advance(30)
    assert dog.silence() == 30
    assert not dog.check()


def test_firing_emits_an_event_with_the_silence_duration() -> None:
    events: list[dict] = []
    dog, clock, _ = _watchdog(threshold=10, events=events)
    clock.advance(15)
    dog.check()
    fired = [event for event in events if event["event"] == "watchdog.fired"]
    assert fired and fired[0]["silence"] == 15.0


def test_start_and_stop_manage_the_monitor_thread() -> None:
    dog, _, _ = _watchdog(threshold=60)
    dog.start(interval=0.01)
    dog.start(interval=0.01)  # idempotent
    dog.stop()
    dog.stop()  # idempotent


def test_the_monitor_thread_actually_checks() -> None:
    """The background loop must call check(), not merely exist."""
    import time

    fired: list[str] = []
    dog = Watchdog(
        threshold_seconds=0.01,
        persist_state=lambda: fired.append("persist"),
        controlled_shutdown=lambda: fired.append("shutdown"),
    )
    dog.start(interval=0.01)
    time.sleep(0.2)
    dog.stop()
    assert fired == ["persist", "shutdown"]
