"""The provider contract every LLM backend satisfies.

One shape for Anthropic, DeepSeek and the offline template bank means the router
can fall down the chain without callers noticing, and it means the template
provider is a *first-class* backend rather than an emergency hack: a full series
can legally be played at zero tokens (book PAGE 67).

Errors are a small taxonomy on purpose. The router needs to distinguish "this
provider is unwell, try the next one" from "this request was malformed, trying
again elsewhere will not help".
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from .token_meter import Usage


class ProviderError(Exception):
    """Base class for anything that stops a provider answering."""


class ProviderUnavailableError(ProviderError):
    """Transient: network, timeout, rate limit, outage. Try the next provider."""


class ProviderRefusedError(ProviderError):
    """Permanent for this request: bad input, content refusal, auth failure."""


@dataclass
class Completion:
    """One provider's answer, with the metadata the report needs."""

    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def provenance(self) -> dict[str, Any]:
        """Per-message attribution shown in the dialogue transcript (FR-LLM-2)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "tokens": self.usage.total,
        }


class Provider(Protocol):
    """What the router requires of any backend."""

    name: str

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        """Produce a completion, or raise a ProviderError."""
        ...

    def healthy(self) -> bool:
        """Cheap liveness probe used for recovery back up the chain."""
        ...


# Substrings meaning "this request is wrong", not "this service is unwell".
PERMANENT_MARKERS = (
    "invalid_request",
    "authentication",
    "permission",
    "not_found",
    "unauthorized",
    "400",
    "401",
    "403",
)


def classify_error(error: Exception) -> ProviderError:
    """Decide whether another provider might do better.

    Walks the `__cause__` chain because the gatekeeper wraps failures in its own
    "failed after N attempts" error — without this, a bad API key would look
    like a transient outage and we would burn retries and a cooldown on
    something no retry can fix.
    """
    parts: list[str] = []
    current: BaseException | None = error
    seen = 0
    while current is not None and seen < 5:
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__
        seen += 1
    text = " | ".join(parts).lower()
    if any(marker in text for marker in PERMANENT_MARKERS):
        return ProviderRefusedError(str(error))
    return ProviderUnavailableError(str(error))
