"""Lazy SDK construction — covered with stub modules, never a real network.

Still fully mocked — no test may touch a real API (guidelines §6.1 rule 7).
"""

from types import SimpleNamespace

import pytest

from najamjad_agent.llm.anthropic_provider import AnthropicProvider
from najamjad_agent.llm.base import ProviderUnavailableError
from najamjad_agent.llm.deepseek_provider import DeepSeekProvider
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig


def _gatekeeper(events: list[dict] | None = None) -> ApiGatekeeper:
    return ApiGatekeeper(
        service="llm",
        config=RateLimitConfig(requests_per_minute=600, max_retries=1),
        emit=(events.append if events is not None else None),
        sleep=lambda _seconds: None,
    )


class FakeAnthropicClient:
    """Mimics the Messages API surface we actually use."""

    def __init__(self, text: str = "hello", error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []
        response = SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            usage=SimpleNamespace(input_tokens=120, output_tokens=30),
        )
        parent = self

        class Messages:
            def create(self, **kwargs):
                parent.calls.append(kwargs)
                if parent.error is not None:
                    raise parent.error
                return response

        self.messages = Messages()


class FakeOpenAIClient:
    """Mimics the chat-completions surface DeepSeek exposes."""

    def __init__(self, text: str = "hello", error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=90, completion_tokens=25),
        )
        parent = self

        class Completions:
            def create(self, **kwargs):
                parent.calls.append(kwargs)
                if parent.error is not None:
                    raise parent.error
                return response

        self.chat = SimpleNamespace(completions=Completions())


def test_anthropic_builds_its_sdk_client_from_a_key(monkeypatch) -> None:
    """Covers the lazy-construction path without a network or a real key."""
    import sys
    from types import ModuleType

    built: list[dict] = []
    module = ModuleType("anthropic")
    module.Anthropic = lambda **kwargs: built.append(kwargs) or FakeAnthropicClient()
    monkeypatch.setitem(sys.modules, "anthropic", module)

    provider = AnthropicProvider(_gatekeeper(), api_key="test-key")
    assert provider.healthy()
    assert provider.complete("s", "u").provider == "anthropic"
    assert built[0]["api_key"] == "test-key"


def test_deepseek_builds_its_sdk_client_with_the_base_url(monkeypatch) -> None:
    import sys
    from types import ModuleType

    built: list[dict] = []
    module = ModuleType("openai")
    module.OpenAI = lambda **kwargs: built.append(kwargs) or FakeOpenAIClient()
    monkeypatch.setitem(sys.modules, "openai", module)

    provider = DeepSeekProvider(_gatekeeper(), api_key="test-key")
    assert provider.complete("s", "u").provider == "deepseek"
    assert built[0]["base_url"].startswith("https://")


def test_an_unhealthy_provider_reports_false_when_construction_fails(monkeypatch) -> None:
    """healthy() must answer, never raise — preflight depends on it."""
    provider = AnthropicProvider(_gatekeeper(), api_key="")
    assert provider.healthy() is False


@pytest.mark.parametrize("provider_class", [AnthropicProvider, DeepSeekProvider])
def test_healthy_returns_false_when_the_sdk_cannot_be_built(provider_class, monkeypatch) -> None:
    """A key that exists but cannot construct a client is still 'not ready'."""
    provider = provider_class(_gatekeeper(), api_key="looks-real")

    def _fail() -> None:
        raise ProviderUnavailableError("sdk missing")

    monkeypatch.setattr(provider, "_ensure_client", _fail)
    assert provider.healthy() is False
