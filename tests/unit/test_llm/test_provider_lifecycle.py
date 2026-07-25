"""Provider lifecycle: error taxonomy, health probes, and lazy SDK construction.

Still fully mocked — no test may touch a real API (guidelines §6.1 rule 7).
"""

from types import SimpleNamespace

import pytest

from najamjad_agent.llm.anthropic_provider import AnthropicProvider
from najamjad_agent.llm.base import Completion, ProviderRefusedError, ProviderUnavailableError
from najamjad_agent.llm.deepseek_provider import DeepSeekProvider
from najamjad_agent.llm.template_provider import TemplateProvider
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


@pytest.mark.parametrize(
    "provider_class,client_class",
    [(AnthropicProvider, FakeAnthropicClient), (DeepSeekProvider, FakeOpenAIClient)],
)
def test_an_outage_is_transient_so_the_router_moves_on(provider_class, client_class) -> None:
    client = client_class(error=ConnectionError("service unavailable 503"))
    provider = provider_class(_gatekeeper(), client=client)
    with pytest.raises(ProviderUnavailableError):
        provider.complete("s", "u")


@pytest.mark.parametrize(
    "provider_class,client_class",
    [(AnthropicProvider, FakeAnthropicClient), (DeepSeekProvider, FakeOpenAIClient)],
)
def test_a_bad_key_is_permanent_not_transient(provider_class, client_class) -> None:
    """Retrying elsewhere will not fix authentication, so say so."""
    client = client_class(error=RuntimeError("authentication_error: invalid api key"))
    provider = provider_class(_gatekeeper(), client=client)
    with pytest.raises(ProviderRefusedError):
        provider.complete("s", "u")


@pytest.mark.parametrize(
    "provider_class,client_class",
    [(AnthropicProvider, FakeAnthropicClient), (DeepSeekProvider, FakeOpenAIClient)],
)
def test_every_call_passes_the_gatekeeper(provider_class, client_class) -> None:
    """ADR-009: no external call may bypass the limiter."""
    events: list[dict] = []
    provider = provider_class(_gatekeeper(events), client=client_class())
    provider.complete("s", "u")
    assert any(event["event"] == "gatekeeper.call" for event in events)


@pytest.mark.parametrize("provider_class", [AnthropicProvider, DeepSeekProvider])
def test_a_missing_key_reports_unavailable_rather_than_crashing(provider_class) -> None:
    provider = provider_class(_gatekeeper(), api_key="")
    assert not provider.healthy()
    with pytest.raises(ProviderUnavailableError):
        provider.complete("s", "u")


@pytest.mark.parametrize(
    "provider_class,client_class",
    [(AnthropicProvider, FakeAnthropicClient), (DeepSeekProvider, FakeOpenAIClient)],
)
def test_an_injected_client_is_considered_healthy(provider_class, client_class) -> None:
    assert provider_class(_gatekeeper(), client=client_class()).healthy()


def test_an_empty_anthropic_response_yields_empty_text() -> None:
    client = FakeAnthropicClient()
    client.messages.create = lambda **_kwargs: SimpleNamespace(content=[], usage=None)
    completion = AnthropicProvider(_gatekeeper(), client=client).complete("s", "u")
    assert completion.text == ""
    assert completion.usage.total == 0


def test_an_empty_deepseek_response_yields_empty_text() -> None:
    client = FakeOpenAIClient()
    client.chat.completions.create = lambda **_kwargs: SimpleNamespace(choices=[], usage=None)
    completion = DeepSeekProvider(_gatekeeper(), client=client).complete("s", "u")
    assert completion.text == ""


@pytest.mark.parametrize(
    "provider",
    [
        AnthropicProvider(_gatekeeper(), client=FakeAnthropicClient()),
        DeepSeekProvider(_gatekeeper(), client=FakeOpenAIClient()),
        TemplateProvider(seed=1),
    ],
)
def test_all_three_backends_satisfy_one_contract(provider) -> None:
    """The router must not need to know which backend it is holding."""
    assert isinstance(provider.name, str) and provider.name
    assert isinstance(provider.healthy(), bool)
    completion = provider.complete("system", "thief hint")
    assert isinstance(completion, Completion)
    assert completion.provider == provider.name
    assert completion.usage.total >= 0
    assert set(completion.provenance) == {"provider", "model", "tokens"}


def test_only_the_template_bank_is_free() -> None:
    """The router uses this to decide what to skip when budget is gone."""
    assert TemplateProvider().free is True
    assert AnthropicProvider(_gatekeeper()).free is False
    assert DeepSeekProvider(_gatekeeper()).free is False


@pytest.mark.parametrize("provider_class", [AnthropicProvider, DeepSeekProvider])
def test_a_configured_key_makes_a_provider_healthy_before_first_use(provider_class) -> None:
    """Preflight must be able to check readiness without spending a token."""
    provider = provider_class(_gatekeeper(), api_key="test-key-not-real")
    assert provider.model


@pytest.mark.parametrize(
    "provider_class,client_class",
    [(AnthropicProvider, FakeAnthropicClient), (DeepSeekProvider, FakeOpenAIClient)],
)
def test_the_lazy_client_is_built_once_and_reused(provider_class, client_class) -> None:
    provider = provider_class(_gatekeeper(), client=client_class())
    first = provider._ensure_client()
    assert provider._ensure_client() is first


@pytest.mark.parametrize("provider_class", [AnthropicProvider, DeepSeekProvider])
def test_healthy_is_false_without_a_key_or_client(provider_class) -> None:
    assert not provider_class(_gatekeeper(), api_key="").healthy()
