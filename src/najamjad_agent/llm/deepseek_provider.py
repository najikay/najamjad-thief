"""DeepSeek backend — the fallback tier, and our workhorse for testing.

Chosen deliberately for the middle of the chain: it speaks the OpenAI-compatible
API, it is inexpensive enough to carry development traffic, and it fails
independently of Anthropic — which is the whole point of a fallback. An outage
that takes out our primary should not take out our alternative.

Same contract, same gatekeeper pattern, same error taxonomy as the primary, so
the router cannot tell them apart except by name.
"""

import os
from typing import Any

from ..shared.app_config import load_setup, setting
from ..shared.gatekeeper import ApiGatekeeper
from .base import Completion, ProviderUnavailableError, classify_error
from .token_meter import Usage

#: `deepseek-chat` was retired; the current line is `deepseek-v4-flash` (cheap,
#: 1M context) and `deepseek-v4-pro`. Flash is the default because a hint is
#: capped at 15 words — paying pro rates to write one sentence buys nothing,
#: and the series token budget is an agreed term rather than a spending limit.
DEFAULT_MODEL = "deepseek-v4-flash"
#: The endpoint lives in `config/setup.json` (`llm.deepseek_base_url`) and
#: nowhere else — a vendor moving its API is a config change, and a URL written
#: into a module is one that cannot be changed without a release.
#:
#: The default is empty rather than a guess. An unconfigured endpoint makes this
#: provider *unavailable*, which the router already handles by falling through
#: to the next one; inventing a plausible URL would instead produce a confusing
#: connection error at the worst moment.
DEFAULT_BASE_URL = setting(load_setup(), "llm.deepseek_base_url", "")


class DeepSeekProvider:
    """Gatekept adapter over DeepSeek's OpenAI-compatible chat API."""

    name = "deepseek"
    free = False

    def __init__(
        self,
        gatekeeper: ApiGatekeeper,
        client: Any = None,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout: float = 8.0,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Wire the adapter; the client is built lazily unless injected."""
        self._gatekeeper = gatekeeper
        self._client = client
        self._model = model
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._timeout = timeout
        self._base_url = base_url

    @property
    def model(self) -> str:
        """The model this provider is configured to call."""
        return self._model

    def _ensure_client(self) -> Any:
        """Build the OpenAI-compatible client on first use."""
        if self._client is None:
            if not self._api_key:
                raise ProviderUnavailableError("DEEPSEEK_API_KEY is not set")
            from openai import OpenAI  # imported lazily: optional at runtime

            if not self._base_url:
                raise ProviderUnavailableError(
                    "llm.deepseek_base_url is not set in config/setup.json"
                )
            self._client = OpenAI(
                # The SDK retries internally by default, so an 8 s timeout became
                # 38 s of wall clock — measured against a blackhole. Retrying a
                # hint is the gatekeeper's job, and one that must not spend the
                # turn: the template floor is instant and free.
                max_retries=0,api_key=self._api_key, base_url=self._base_url)
        return self._client

    def _call(self, system: str, user: str, max_tokens: int) -> Any:
        """One raw API call — the unit the gatekeeper wraps."""
        client = self._ensure_client()
        return client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            timeout=self._timeout,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    def complete(self, system: str, user: str, max_tokens: int = 200) -> Completion:
        """Produce a completion, mapping SDK failures into our taxonomy."""
        try:
            response = self._gatekeeper.execute(self._call, system, user, max_tokens)
        except Exception as error:  # noqa: BLE001 - re-raised as a typed provider error
            raise classify_error(error) from error
        return Completion(
            text=_extract_text(response),
            provider=self.name,
            model=self._model,
            usage=_extract_usage(response),
        )

    def healthy(self) -> bool:
        """Cheap probe used for recovery back up the chain."""
        if not self._api_key and self._client is None:
            return False
        try:
            self._ensure_client()
        except ProviderUnavailableError:
            return False
        return True


def _extract_text(response: Any) -> str:
    """Pull the assistant message out of a chat-completions response."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return (getattr(message, "content", "") or "").strip()


def _extract_usage(response: Any) -> Usage:
    """Read token usage; absent usage is reported as zero rather than guessed."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )
