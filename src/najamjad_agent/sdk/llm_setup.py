"""Building the hint writer: which models speak, and what they cost.

Split out of `bootstrap` because it is a decision rather than wiring — which
vendors are tried, in what order, and under whose budget — and because
bootstrap crossed the size cap once the chain stopped being one hardcoded
entry.

What this fixes is worth stating plainly. `bootstrap._speaker` used to wire
`[TemplateProvider]` alone while its docstring claimed "real providers when
configured". So `llm.primary`, `llm.fallback` and `llm.model` were inert, every
hint in every match was template-generated, and — because nothing built a
`TokenMeter` either — every token figure in every emailed report was `0` by
construction. The report field, the budget panel, and the 200k agreed cap were
all reading a counter nothing incremented.

Two ordering rules hold the design together:

* **Templates are last and unconditional.** They cost no tokens and cannot
  fail, which is what lets a total vendor outage degrade hint *quality*
  instead of ending the game (book PAGE 67).
* **A vendor with no API key is not wired at all.** The first version built
  them anyway, reasoning that the router would skip an unavailable provider.
  Measured, that cost **20 seconds on the first hint of a match**: a missing
  key raises, the gatekeeper retries it three times five seconds apart, and it
  does so once per vendor. The turn deadline is 30 s. A provider that cannot
  authenticate is not a fallback, it is a way to lose a game to our own retry
  policy, so its absence is reported as an event instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shared.app_config import load_setup, setting

ANTHROPIC = "anthropic"
DEEPSEEK = "deepseek"
#: Which environment variable each vendor authenticates with. Absent means the
#: vendor is skipped, not retried.
API_KEYS = {ANTHROPIC: "ANTHROPIC_API_KEY", DEEPSEEK: "DEEPSEEK_API_KEY"}


def _gatekeeper(service: str, bus: Any) -> Any:
    """The rate limiter every outbound vendor call goes through.

    Not optional and not shared with the peer transport: an opponent is a
    protocol partner, a vendor is a metered API, and throttling them by the
    same rule was how we once rejected a legitimate turn mid-series.
    """
    from ..shared.gatekeeper import ApiGatekeeper
    from ..shared.rate_limits import for_service, load_rate_limits

    limits = load_rate_limits(
        Path(setting(load_setup(), "paths.rate_limits", "config/rate_limits.json"))
    )
    return ApiGatekeeper(service=service, config=for_service(limits, service), emit=bus.publish)


def paid_provider(name: str, manager: Any, bus: Any) -> Any:
    """One configured vendor, or None if it is unnamed or uncredentialed."""
    import os

    if name not in API_KEYS:
        return None
    if not os.environ.get(API_KEYS[name], ""):
        bus.publish(
            {
                "event": "llm.provider_skipped",
                "provider": name,
                "reason": f"{API_KEYS[name]} is not set",
            }
        )
        return None
    model = str(manager.get("llm.model", "") or "")
    if name == ANTHROPIC:
        from ..llm.anthropic_provider import AnthropicProvider

        keywords = {"model": model} if model else {}
        return AnthropicProvider(gatekeeper=_gatekeeper(ANTHROPIC, bus), **keywords)
    if name == DEEPSEEK:
        from ..llm.deepseek_provider import DeepSeekProvider

        return DeepSeekProvider(gatekeeper=_gatekeeper(DEEPSEEK, bus))
    return None


def token_meter(manager: Any, bus: Any) -> Any:
    """The budget the series was agreed under (book rule 54).

    The series cap is an *agreed term*: exceeding it is a breach, not an
    expense. The project ceiling is a runaway-loop backstop, deliberately far
    above any measured need, and never a reason to play worse.
    """
    from ..llm.token_meter import TokenMeter

    return TokenMeter(
        series_limit=int(manager.get("llm.series_token_budget", 200_000)),
        project_limit=int(manager.get("llm.project_token_budget", 5_000_000)),
        emit=bus.publish,
    )


def build_speaker(manager: Any, bus: Any, meter: Any = None) -> Any:
    """The hint writer: configured vendors first, templates as the floor."""
    from ..llm.router import LLMRouter
    from ..llm.speaker import Speaker
    from ..llm.template_provider import TemplateProvider

    template = TemplateProvider(map_area=str(manager.get("world.map_area", "")))
    chain = [
        provider
        for provider in (
            paid_provider(str(manager.get("llm.primary", "") or ""), manager, bus),
            paid_provider(str(manager.get("llm.fallback", "") or ""), manager, bus),
        )
        if provider is not None
    ]
    return Speaker(
        router=LLMRouter(providers=[*chain, template], meter=meter, emit=bus.publish),
        template=template,
        arena=str(manager.get("world.map_area", "")),
        hint_max_words=int(manager.get("world.hint_max_words", 15)),
        every_n_steps=int(manager.get("llm.every_n_steps", 1)),
        emit=bus.publish,
    )
