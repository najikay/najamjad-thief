"""Tests for deadline tracking and sealed timeout evidence."""

from najamjad_agent.domain.crypto import verify
from najamjad_agent.net.deadline import DeadlineTracker


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        self.value += 0.5
        return self.value


def _tracker(events: list[dict] | None = None, **kwargs) -> DeadlineTracker:
    return DeadlineTracker(
        clock=FakeClock().now,
        emit=(events.append if events is not None else None),
        **kwargs,
    )


def test_deadline_defaults_match_appendix_f() -> None:
    tracker = DeadlineTracker()
    assert tracker.response_timeout == 30.0
    assert tracker.max_retries == 3


def test_started_deadline_has_a_budget() -> None:
    tracker = _tracker()
    deadline = tracker.start("opponent-turn", timeout=10)
    assert deadline.expires_at - deadline.started_at == 10
    assert deadline.label == "opponent-turn"


def test_remaining_never_goes_negative() -> None:
    tracker = _tracker()
    deadline = tracker.start("x", timeout=1)
    assert deadline.remaining(deadline.expires_at + 100) == 0.0


def test_expired_reports_when_the_budget_is_spent() -> None:
    tracker = _tracker()
    deadline = tracker.start("x", timeout=1)
    assert not deadline.expired(deadline.started_at)
    assert deadline.expired(deadline.expires_at + 0.1)


def test_await_value_returns_the_first_result() -> None:
    tracker = _tracker()
    assert tracker.await_value("turn", lambda _t: {"step": 1}) == {"step": 1}
    assert tracker.timeouts == []


def test_await_value_retries_then_succeeds() -> None:
    events: list[dict] = []
    tracker = _tracker(events, max_retries=3)
    attempts = {"n": 0}

    def poll(_timeout: float):
        attempts["n"] += 1
        return "arrived" if attempts["n"] == 3 else None

    assert tracker.await_value("turn", poll) == "arrived"
    assert attempts["n"] == 3
    assert sum(1 for e in events if e["event"] == "deadline.expired") == 2


def test_await_value_gives_up_cleanly_instead_of_hanging() -> None:
    """Book rule 6: a missed deadline is a failure, never patience."""
    events: list[dict] = []
    tracker = _tracker(events, max_retries=3)
    assert tracker.await_value("turn", lambda _t: None) is None
    assert len(tracker.timeouts) == 1
    assert any(e["event"] == "deadline.timeout" for e in events)


def test_timeout_records_what_was_waited_for() -> None:
    tracker = _tracker(response_timeout=30.0, max_retries=3)
    tracker.await_value("opponent-turn", lambda _t: None)
    entry = tracker.timeouts[0]
    assert entry["label"] == "opponent-turn"
    assert entry["attempts"] == 3
    assert entry["waited_seconds"] == 90.0


def test_timeout_evidence_is_sealed_and_verifiable() -> None:
    """Improves on the reference's unverifiable self-awarded timeout win."""
    tracker = _tracker()
    tracker.await_value("opponent-turn", lambda _t: None)
    record = tracker.evidence(step=12, role="police", sub_game=1)
    assert verify(record.payload, record.nonce, record.commit)
    assert record.payload["type"] == "timeout_evidence"
    assert record.payload["step"] == 12
    assert record.payload["timeouts"][0]["label"] == "opponent-turn"


def test_evidence_cannot_be_edited_after_sealing() -> None:
    tracker = _tracker()
    tracker.await_value("turn", lambda _t: None)
    record = tracker.evidence(step=1, role="thief", sub_game=1)
    tampered = {**record.payload, "timeouts": []}
    assert not verify(tampered, record.nonce, record.commit)


def test_events_are_emitted_for_every_phase() -> None:
    events: list[dict] = []
    tracker = _tracker(events, max_retries=1)
    tracker.await_value("turn", lambda _t: None)
    names = {event["event"] for event in events}
    assert {"deadline.started", "deadline.expired", "deadline.timeout"} <= names
