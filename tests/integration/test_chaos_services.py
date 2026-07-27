"""Chaos in the services around the game (T-2115..T-2118, T-2120).

Everything here is something that can fail *while a match is running*, where the
only acceptable outcome is that the game continues or ends cleanly. A tunnel, a
model provider and a mailbox are all things we do not control; none of them may
be able to convert their bad day into our technical loss.
"""

import time
from pathlib import Path

import pytest

from najamjad_agent.llm.base import ProviderError, ProviderUnavailableError
from najamjad_agent.llm.router import LLMRouter
from najamjad_agent.llm.template_provider import TemplateProvider
from najamjad_agent.net.deadline import DeadlineTracker
from najamjad_agent.net.tunnel import Tunnel
from najamjad_agent.reporting.gmail_sender import GmailError, GmailSender
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import for_service, load_rate_limits


class DeadProvider:
    """A provider that is down for the duration."""

    name = "dead"
    free = False

    def __init__(self, error=ProviderUnavailableError) -> None:
        self.calls = 0
        self._error = error

    def complete(self, *_args, **_kwargs):
        self.calls += 1
        raise self._error("service unavailable")


class FakeProcess:
    """A child process we can kill on demand."""

    def __init__(self) -> None:
        self.alive = True
        self.terminated = 0

    def poll(self):
        return None if self.alive else 1

    def terminate(self) -> None:
        self.terminated += 1
        self.alive = False

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.alive = False


# --------------------------------------------------------------------------- tunnel


def test_a_tunnel_that_dies_is_restarted_and_keeps_its_hostname():
    """T-2115. The hostname is permanent, so the opponent's saved URL survives
    a restart — which is the entire reason we use a *named* tunnel (ADR-004)."""
    processes: list[FakeProcess] = []

    def spawn(_command):
        processes.append(FakeProcess())
        return processes[-1]

    tunnel = Tunnel("cloudflare", "cop.4laboratory.com", 8802, name="najamjad-cop", spawn=spawn)
    tunnel.start()
    url_before = tunnel.public_url

    assert tunnel.check() is False, "a healthy tunnel needs no restart"

    processes[0].alive = False  # the tunnel dies mid-series
    assert tunnel.check() is True, "check() reports that it had to restart"

    assert tunnel.restarts == 1
    assert len(processes) == 2, "a replacement process was actually spawned"
    assert tunnel.public_url == url_before, "a restart must not change our public name"


def test_stopping_a_tunnel_terminates_the_child():
    """An unstopped tunnel points a public hostname at a dead port."""
    processes: list[FakeProcess] = []
    tunnel = Tunnel("cloudflare", "cop.4laboratory.com", 8802, name="najamjad-cop",
                    spawn=lambda _c: processes.append(FakeProcess()) or processes[-1])
    tunnel.start()

    tunnel.stop()

    assert processes[0].terminated == 1


# --------------------------------------------------------------------------- LLM


def test_a_total_llm_outage_falls_through_to_the_template_floor():
    """T-2116. Both paid providers down: the game must continue on templates,
    because a hint is mandatory (rule 26) and an outage is not our opponent's
    problem to wait for."""
    primary, secondary = DeadProvider(), DeadProvider(ProviderError)
    template = TemplateProvider(seed=3)
    events: list[dict] = []
    router = LLMRouter(providers=[primary, secondary, template], emit=events.append)

    reply = router.complete("system", "user")

    assert reply.text, "the floor must still produce a hint"
    assert router.active == "template"
    assert primary.calls and secondary.calls, "both paid providers were tried first"
    assert any(e["event"].startswith("llm.") for e in events), "the switch must be visible"


def test_the_outage_is_reported_rather_than_hidden():
    events: list[dict] = []
    router = LLMRouter(providers=[DeadProvider(), TemplateProvider(seed=1)], emit=events.append)

    router.complete("system", "user")

    names = {event["event"] for event in events}
    assert names & {"llm.provider_failed", "llm.provider_changed", "llm.fallback"}, names


def test_every_provider_failing_raises_rather_than_returning_nothing():
    """With no template floor configured there is no honest answer to invent."""
    router = LLMRouter(providers=[DeadProvider(), DeadProvider()])

    with pytest.raises(ProviderError):
        router.complete("system", "user")


# --------------------------------------------------------------------------- Gmail


def test_a_429_storm_dead_letters_instead_of_resending_blindly(tmp_path):
    """T-2117. Blind resends against a rate-limited mailbox risk the account —
    the report is parked with its reason instead, and the artifact still exists."""
    attachment = tmp_path / "result.json"
    attachment.write_text("{}", encoding="utf-8")
    dead_letters = tmp_path / "dead"
    calls = {"n": 0}

    def always_429(_raw):
        calls["n"] += 1
        raise GmailError("429 Too Many Requests: user-rate limit exceeded")

    limits = load_rate_limits(Path("config/rate_limits.json"))
    sender = GmailSender(
        gatekeeper=ApiGatekeeper(service="gmail", config=for_service(limits, "gmail")),
        recipient="them@example.com",
        service=object(),
        mode="send",
        dead_letter_dir=dead_letters,
    )
    sender._dispatch = always_429

    # Parked *and* raised, deliberately: the caller must not be able to treat an
    # undelivered report as sent, and rule 35 punishes not reporting.
    with pytest.raises(GmailError, match="not delivered"):
        sender.send_report(attachment, subject="result")

    assert calls["n"] <= 3, "a storm must not become an unbounded retry loop"
    parked = list(dead_letters.iterdir())
    assert parked, "the report must be recoverable, not lost"
    assert parked[0].name.startswith("UNSENT_"), "and obviously unsent to a human"


# --------------------------------------------------------------------------- clock


def test_deadlines_are_immune_to_wall_clock_skew_by_construction():
    """T-2118. An NTP correction or a laptop resuming from sleep moves the wall
    clock; it must not move a deadline.

    The protection is structural rather than defensive: the tracker's clock is
    `time.monotonic`, which cannot go backwards and is unaffected by wall-clock
    changes. Asserting that is more honest than clamping arithmetic against a
    case the real clock cannot produce.
    """
    assert DeadlineTracker().clock is time.monotonic

    before = time.monotonic()
    tracker = DeadlineTracker(response_timeout=30.0)
    deadline = tracker.start("opponent-turn")

    assert deadline.expires_at - deadline.started_at == pytest.approx(30.0)
    assert deadline.started_at >= before


def test_a_deadline_expires_rather_than_wrapping_when_time_runs_past_it():
    """A long stall must read as expired, never as a fresh budget."""
    tracker = DeadlineTracker(response_timeout=30.0, clock=lambda: 100.0)
    deadline = tracker.start("opponent-turn")

    assert deadline.remaining(now=115.0) == pytest.approx(15.0)
    assert deadline.remaining(now=400.0) == 0.0
    assert deadline.expired(now=400.0) is True


def test_preflight_can_surface_a_skewed_clock():
    """The operator-facing half of T-2118: skew is reportable, not silent."""
    from najamjad_agent.net.preflight import run_check

    def skewed() -> str:
        raise ValueError("system clock differs from NTP by 42 s")

    result = run_check("clock", skewed)

    assert result.passed is False
    assert "42 s" in result.detail


# --------------------------------------------------------------------------- soak


@pytest.mark.slow
def test_three_consecutive_series_leave_no_residue():
    """T-2120. Queues must return to zero and history must not grow without
    bound across a league evening's worth of play."""
    from najamjad_agent.net.inbox import Inboxes

    inboxes = Inboxes()
    for series in range(3):
        for step in range(1, 36):
            inboxes.accept("turn", {"step": step + series * 100, "sender": "thief",
                                    "commit": f"{step:064d}", "hint": "x", "smell_grid": {}})
            assert inboxes.poll("turn", timeout=0.01) is not None

    assert inboxes.poll("turn", timeout=0.01) is None, "the queue must drain to empty"


@pytest.mark.slow
def test_the_event_log_does_not_slow_down_as_it_grows(tmp_path):
    """A log that degrades over a series would make late turns miss deadlines."""
    from najamjad_agent.shared.events import EventBus

    bus = EventBus(path=tmp_path / "events.jsonl")
    bus.publish({"event": "warm"})

    def elapsed_for(count: int) -> float:
        start = time.monotonic()
        for index in range(count):
            bus.publish({"event": "turn.sent", "step": index})
        return time.monotonic() - start

    first, last = elapsed_for(200), None
    for _ in range(4):
        last = elapsed_for(200)

    assert last is not None
    assert last < first * 5 + 0.5, f"logging degraded: {first:.3f}s then {last:.3f}s"
    bus.close()


def test_the_workspace_path_is_not_required_to_exist_up_front(tmp_path):
    """A fresh clone has no workspace; the first event must create it."""
    from najamjad_agent.shared.events import EventBus

    bus = EventBus(path=tmp_path / "deep" / "nested" / "events.jsonl")
    bus.publish({"event": "first"})
    bus.close()

    assert Path(tmp_path / "deep" / "nested" / "events.jsonl").exists()
