"""Tests for router visibility: who is speaking, and what it cost."""

import pytest

from najamjad_agent.llm.base import (
    Completion,
    ProviderUnavailableError,
)
from najamjad_agent.llm.router import LLMRouter
from najamjad_agent.llm.template_provider import TemplateProvider
from najamjad_agent.llm.token_meter import TokenMeter, Usage


class FakeProvider:
    """A backend we can make fail on demand."""

    def __init__(self, name: str, error: Exception | None = None, free: bool = False) -> None:
        self.name = name
        self.free = free
        self.error = error
        self.calls = 0
        self.is_healthy = True

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Completion(
            text=f"reply from {self.name}",
            provider=self.name,
            model=f"{self.name}-model",
            usage=Usage(input_tokens=100, output_tokens=20),
        )

    def healthy(self) -> bool:
        return self.is_healthy


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value


@pytest.fixture()
def events() -> list[dict]:
    return []


def test_the_active_provider_is_queryable_for_the_badge(events: list[dict]) -> None:
    """FR-LLM-2: we must always be able to say who is speaking."""
    router = LLMRouter(
        [FakeProvider("anthropic", error=ProviderUnavailableError("x")), FakeProvider("deepseek")],
        emit=events.append,
    )
    router.complete("sys", "user")
    assert router.active == "deepseek"


def test_a_provider_switch_is_announced(events: list[dict]) -> None:
    router = LLMRouter(
        [FakeProvider("anthropic", error=ProviderUnavailableError("x")), FakeProvider("deepseek")],
        emit=events.append,
    )
    router.complete("sys", "user")
    changed = [event for event in events if event["event"] == "llm.provider_changed"]
    assert changed and changed[0]["previous"] == "anthropic"


def test_each_completion_carries_provenance(events: list[dict]) -> None:
    """Per-message attribution in the dialogue transcript."""
    router = LLMRouter([FakeProvider("anthropic")], emit=events.append)
    completion = router.complete("sys", "user")
    assert completion.provenance == {
        "provider": "anthropic",
        "model": "anthropic-model",
        "tokens": 120,
    }
    assert any(event["event"] == "llm.completion" for event in events)


def test_status_reports_every_provider_for_the_dashboard() -> None:
    router = LLMRouter([FakeProvider("anthropic"), TemplateProvider()])
    router.complete("sys", "user")
    status = router.status()
    assert [entry["provider"] for entry in status] == ["anthropic", "template"]
    assert status[0]["active"] is True


def test_usage_is_metered_per_purpose_and_game() -> None:
    meter = TokenMeter(series_limit=10_000, project_limit=50_000)
    router = LLMRouter([FakeProvider("anthropic")], meter=meter)
    router.complete("sys", "user", purpose="negotiation", sub_game=2)
    assert meter.report()["by_purpose"]["negotiation"] == 120
    assert meter.report()["per_sub_game"]["2"] == 120


def test_paid_providers_are_skipped_when_the_budget_is_gone(events: list[dict]) -> None:
    """The free floor keeps playing; the paid tiers stand down."""
    meter = TokenMeter(series_limit=100, project_limit=100)
    meter.record(Usage(100, 0), model="x")
    router = LLMRouter(
        [FakeProvider("anthropic"), TemplateProvider(seed=2)], meter=meter, emit=events.append
    )
    assert router.complete("sys", "thief").provider == "template"
    assert any(event["event"] == "llm.budget_skip" for event in events)
