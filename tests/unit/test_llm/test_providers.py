"""Provider tests — fully mocked; no test may touch a real API (guidelines §6.1).

Both paid backends and the template bank are held to one contract, so the router
genuinely cannot tell them apart except by name.
"""

from types import SimpleNamespace

from najamjad_agent.llm.anthropic_provider import AnthropicProvider
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


def test_anthropic_maps_a_response_into_a_completion() -> None:
    provider = AnthropicProvider(_gatekeeper(), client=FakeAnthropicClient("north side"))
    completion = provider.complete("system", "user")
    assert completion.text == "north side"
    assert completion.provider == "anthropic"
    assert completion.usage.total == 150


def test_anthropic_sends_system_and_user_content() -> None:
    client = FakeAnthropicClient()
    AnthropicProvider(_gatekeeper(), client=client).complete("be terse", "say hi", max_tokens=64)
    call = client.calls[0]
    assert call["system"] == "be terse"
    assert call["messages"][0]["content"] == "say hi"
    assert call["max_tokens"] == 64


def test_deepseek_maps_a_response_into_a_completion() -> None:
    provider = DeepSeekProvider(_gatekeeper(), client=FakeOpenAIClient("by the river"))
    completion = provider.complete("system", "user")
    assert completion.text == "by the river"
    assert completion.provider == "deepseek"
    assert completion.usage.total == 115


def test_deepseek_sends_both_message_roles() -> None:
    client = FakeOpenAIClient()
    DeepSeekProvider(_gatekeeper(), client=client).complete("be terse", "say hi")
    roles = [message["role"] for message in client.calls[0]["messages"]]
    assert roles == ["system", "user"]
