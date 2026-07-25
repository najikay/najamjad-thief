"""The provider chain: Anthropic → DeepSeek → template (ADR-003).

Three rules shape this module:

1. **Never fail the turn.** The chain ends at the template bank, which cannot
   fail and costs nothing, so a dead API is a quality regression rather than a
   lost game.
2. **Always say who spoke.** Assignment 6's negotiation was invisible partly
   because nobody could tell which model produced what. Every switch emits an
   event, every completion carries provenance, and the current provider is
   queryable for the dashboard badge (FR-LLM-2).
3. **Recover upward.** A provider that failed once is retried after a cooldown,
   so a thirty-second outage does not demote us to templates for a whole series.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .base import (
    Completion,
    Provider,
    ProviderError,
    ProviderRefusedError,
    ProviderUnavailableError,
)
from .token_meter import TokenMeter

DEFAULT_COOLDOWN_SEC = 60.0


@dataclass
class ProviderState:
    """Health bookkeeping for one backend."""

    provider: Provider
    failures: int = 0
    unavailable_until: float = 0.0

    def available(self, now: float) -> bool:
        """True when this provider may be tried again."""
        return now >= self.unavailable_until


@dataclass
class LLMRouter:
    """Tries each provider in order, degrading and recovering with health."""

    providers: list[Provider]
    meter: TokenMeter | None = None
    emit: Callable[[dict], None] | None = None
    clock: Callable[[], float] = time.monotonic
    cooldown: float = DEFAULT_COOLDOWN_SEC
    _states: list[ProviderState] = field(init=False, default_factory=list)
    _active: str = field(init=False, default="")

    def __post_init__(self) -> None:
        """Wrap each provider with its health state."""
        if not self.providers:
            raise ValueError("the router needs at least one provider (the template bank)")
        self._states = [ProviderState(provider=provider) for provider in self.providers]
        self._active = self.providers[0].name

    @property
    def active(self) -> str:
        """Which backend answered most recently — the UI badge (FR-LLM-2)."""
        return self._active

    def status(self) -> list[dict[str, Any]]:
        """Per-provider health for the dashboard."""
        now = self.clock()
        return [
            {
                "provider": state.provider.name,
                "available": state.available(now),
                "failures": state.failures,
                "active": state.provider.name == self._active,
            }
            for state in self._states
        ]

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 200,
        purpose: str = "hint",
        sub_game: int = 0,
    ) -> Completion:
        """Get a completion from the best available provider."""
        now = self.clock()
        errors: list[str] = []
        for index, state in enumerate(self._states):
            if not self._may_use(state, index, now):
                continue
            try:
                completion = state.provider.complete(system, user, max_tokens)
            except ProviderRefusedError as error:
                # Permanent for this request: another provider may still oblige,
                # but we record it distinctly so the operator can see the cause.
                errors.append(f"{state.provider.name}: refused ({error})")
                self._event("llm.refused", provider=state.provider.name, error=str(error))
                continue
            except (ProviderUnavailableError, ProviderError) as error:
                errors.append(f"{state.provider.name}: unavailable ({error})")
                self._demote(state, str(error))
                continue
            self._promote(state)
            self._record(completion, purpose, sub_game)
            return completion
        raise ProviderError(f"every provider failed: {'; '.join(errors)}")

    def _may_use(self, state: ProviderState, index: int, now: float) -> bool:
        """Skip a cooling-down provider, and skip paid ones with no budget."""
        if not state.available(now):
            return False
        is_free = getattr(state.provider, "free", False)
        if not is_free and self.meter is not None and not self.meter.may_spend():
            self._event("llm.budget_skip", provider=state.provider.name)
            return False
        return True

    def _demote(self, state: ProviderState, reason: str) -> None:
        """Mark a provider unwell and announce the switch."""
        state.failures += 1
        state.unavailable_until = self.clock() + self.cooldown
        self._event(
            "llm.degraded",
            provider=state.provider.name,
            reason=reason,
            cooldown=self.cooldown,
        )

    def _promote(self, state: ProviderState) -> None:
        """Record which provider answered, announcing any change."""
        state.failures = 0
        if state.provider.name != self._active:
            self._event("llm.provider_changed", provider=state.provider.name, previous=self._active)
            self._active = state.provider.name

    def _record(self, completion: Completion, purpose: str, sub_game: int) -> None:
        """Meter the spend and publish provenance for the transcript."""
        if self.meter is not None and completion.usage.total:
            self.meter.record(completion.usage, completion.model, purpose, sub_game)
        self._event("llm.completion", purpose=purpose, **completion.provenance)

    def recover(self) -> list[str]:
        """Probe cooling-down providers so we climb back up the chain."""
        now = self.clock()
        recovered: list[str] = []
        for state in self._states:
            if state.available(now) or not state.provider.healthy():
                continue
            state.unavailable_until = 0.0
            recovered.append(state.provider.name)
            self._event("llm.recovered", provider=state.provider.name)
        return recovered

    def _event(self, name: str, **fields: Any) -> None:
        if self.emit is not None:
            self.emit({"event": name, **fields})
