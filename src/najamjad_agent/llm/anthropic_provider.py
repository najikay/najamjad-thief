"""Anthropic backend — our primary voice for hints and negotiation prose.

The SDK client is injected rather than constructed here, which is what lets the
whole layer be tested without a network or an API key (guidelines §6.1 rule 7:
no test may depend on an external service).

Every call goes through the `anthropic` gatekeeper, so rate limits and retries
come from `config/rate_limits.json` instead of being reinvented per provider.
Errors are mapped into the shared taxonomy so the router can tell "try the next
provider" from "this request will fail everywhere".
"""

import os
from typing import Any

from ..shared.gatekeeper import ApiGatekeeper
from .base import Completion, ProviderUnavailableError, classify_error
from .token_meter import Usage

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicProvider:
    """Thin, gatekept adapter over the Anthropic Messages API."""

    name = "anthropic"
    free = False

    def __init__(
        self,
        gatekeeper: ApiGatekeeper,
        client: Any = None,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout: float = 8.0,
    ) -> None:
        """Wire the adapter; the client is built lazily unless injected."""
        self._gatekeeper = gatekeeper
        self._client = client
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout

    @property
    def model(self) -> str:
        """The model this provider is configured to call."""
        return self._model

    def _ensure_client(self) -> Any:
        """Build the SDK client on first use, so import never needs a key."""
        if self._client is None:
            if not self._api_key:
                raise ProviderUnavailableError("ANTHROPIC_API_KEY is not set")
            from anthropic import Anthropic  # imported lazily: optional at runtime

            self._client = Anthropic(
                # The SDK retries internally by default, so an 8 s timeout became
                # 38 s of wall clock — measured against a blackhole. Retrying a
                # hint is the gatekeeper's job, and one that must not spend the
                # turn: the template floor is instant and free.
                max_retries=0,api_key=self._api_key)
        return self._client

    def _call(self, system: str, user: str, max_tokens: int) -> Any:
        """One raw API call — the unit the gatekeeper wraps."""
        client = self._ensure_client()
        return client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            timeout=self._timeout,
            system=system,
            messages=[{"role": "user", "content": user}],
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
        """Cheap probe used for recovery: a key and a client are enough."""
        if not self._api_key and self._client is None:
            return False
        try:
            self._ensure_client()
        except ProviderUnavailableError:
            return False
        return True


def _extract_text(response: Any) -> str:
    """Pull the text out of a Messages response, tolerating shape drift."""
    blocks = getattr(response, "content", None) or []
    parts = [getattr(block, "text", "") for block in blocks]
    return "".join(part for part in parts if part).strip()


def _extract_usage(response: Any) -> Usage:
    """Read token usage; absent usage is reported as zero rather than guessed."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
    )
