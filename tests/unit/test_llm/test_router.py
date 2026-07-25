"""Tests for the provider chain: degradation, recovery, and visibility."""

import pytest

from najamjad_agent.llm.base import (
    Completion,
    ProviderError,
    ProviderRefusedError,
    ProviderUnavailableError,
)
from najamjad_agent.llm.router import LLMRouter
from najamjad_agent.llm.template_provider import TemplateProvider
from najamjad_agent.llm.token_meter import Usage


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


def test_the_first_healthy_provider_answers(events: list[dict]) -> None:
    primary = FakeProvider("anthropic")
    secondary = FakeProvider("deepseek")
    router = LLMRouter([primary, secondary], emit=events.append)
    completion = router.complete("sys", "user")
    assert completion.provider == "anthropic"
    assert secondary.calls == 0


def test_an_unavailable_provider_falls_through_to_the_next(events: list[dict]) -> None:
    primary = FakeProvider("anthropic", error=ProviderUnavailableError("503"))
    secondary = FakeProvider("deepseek")
    router = LLMRouter([primary, secondary], emit=events.append)
    assert router.complete("sys", "user").provider == "deepseek"
    assert any(event["event"] == "llm.degraded" for event in events)


def test_the_chain_ends_at_the_template_bank(events: list[dict]) -> None:
    """A dead API must cost quality, never the turn (book PAGE 67)."""
    router = LLMRouter(
        [
            FakeProvider("anthropic", error=ProviderUnavailableError("down")),
            FakeProvider("deepseek", error=ProviderUnavailableError("down")),
            TemplateProvider(seed=1),
        ],
        emit=events.append,
    )
    completion = router.complete("sys", "thief hint please")
    assert completion.provider == "template"
    assert completion.usage.total == 0


def test_a_refusal_is_distinguished_from_an_outage(events: list[dict]) -> None:
    """A refused request should not mark a healthy provider as unwell."""
    primary = FakeProvider("anthropic", error=ProviderRefusedError("content policy"))
    router = LLMRouter([primary, FakeProvider("deepseek")], emit=events.append)
    router.complete("sys", "user")
    assert any(event["event"] == "llm.refused" for event in events)
    assert not any(event["event"] == "llm.degraded" for event in events)


def test_every_provider_failing_raises_clearly() -> None:
    router = LLMRouter(
        [
            FakeProvider("anthropic", error=ProviderUnavailableError("a")),
            FakeProvider("deepseek", error=ProviderUnavailableError("b")),
        ]
    )
    with pytest.raises(ProviderError, match="every provider failed"):
        router.complete("sys", "user")


def test_a_router_needs_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        LLMRouter([])


def test_a_demoted_provider_is_skipped_during_cooldown() -> None:
    clock = Clock()
    primary = FakeProvider("anthropic", error=ProviderUnavailableError("down"))
    router = LLMRouter([primary, FakeProvider("deepseek")], clock=clock.now, cooldown=60)
    router.complete("sys", "user")
    router.complete("sys", "user")
    assert primary.calls == 1, "a cooling-down provider is not retried every turn"


def test_cooldown_expiry_lets_the_primary_be_tried_again() -> None:
    clock = Clock()
    primary = FakeProvider("anthropic", error=ProviderUnavailableError("down"))
    router = LLMRouter([primary, FakeProvider("deepseek")], clock=clock.now, cooldown=60)
    router.complete("sys", "user")
    clock.value = 61
    router.complete("sys", "user")
    assert primary.calls == 2


def test_health_probes_promote_us_back_up_the_chain(events: list[dict]) -> None:
    """A thirty-second outage must not demote us for a whole series."""
    clock = Clock()
    primary = FakeProvider("anthropic", error=ProviderUnavailableError("down"))
    router = LLMRouter([primary, FakeProvider("deepseek")], emit=events.append, clock=clock.now)
    router.complete("sys", "user")
    primary.error = None
    assert router.recover() == ["anthropic"]
    assert router.complete("sys", "user").provider == "anthropic"
    assert any(event["event"] == "llm.recovered" for event in events)


def test_an_unhealthy_provider_is_not_recovered() -> None:
    primary = FakeProvider("anthropic", error=ProviderUnavailableError("down"))
    router = LLMRouter([primary, FakeProvider("deepseek")])
    router.complete("sys", "user")
    primary.is_healthy = False
    assert router.recover() == []
