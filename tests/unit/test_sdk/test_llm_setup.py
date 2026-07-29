"""Wiring the hint writer and the token budget (T-2426).

`bootstrap._speaker` used to wire `[TemplateProvider]` alone while its
docstring said "real providers when configured", so `llm.primary`,
`llm.fallback` and `llm.model` were inert and every hint in every match was
template-generated. Nothing built a `TokenMeter` either, so every token figure
in every emailed report was 0 by construction.

The sharp edge found while fixing it: building a vendor that has no API key
cost **20 seconds on the first hint**, because a missing key raises and the
gatekeeper retries it three times five seconds apart, once per vendor. The turn
deadline is 30 s. These tests pin both the wiring and that cost.
"""

import pytest

from najamjad_agent.sdk.llm_setup import build_speaker, paid_provider, token_meter


class Bus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(event)


class Manager:
    def __init__(self, **values) -> None:
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.fixture()
def keys(monkeypatch):
    """Control vendor credentials without touching the real environment."""

    def apply(**present):
        for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        for name, value in present.items():
            monkeypatch.setenv(name, value)

    return apply


def names(speaker) -> list[str]:
    return [provider.name for provider in speaker._router.providers]


def test_the_templates_are_always_the_last_resort(keys):
    """Zero tokens and cannot fail, so a total vendor outage degrades hint
    quality rather than ending the game (book PAGE 67)."""
    keys()

    speaker = build_speaker(Manager(), Bus())

    assert names(speaker)[-1] == "template"


def test_configured_vendors_are_actually_wired(keys):
    """The whole point: these keys used to be inert."""
    keys(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k")
    manager = Manager(**{"llm.primary": "anthropic", "llm.fallback": "deepseek"})

    assert names(build_speaker(manager, Bus())) == ["anthropic", "deepseek", "template"]


def test_the_configured_order_is_respected(keys):
    """`llm.primary` means first, not merely present."""
    keys(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k")
    manager = Manager(**{"llm.primary": "deepseek", "llm.fallback": "anthropic"})

    assert names(build_speaker(manager, Bus()))[:2] == ["deepseek", "anthropic"]


def test_a_vendor_without_credentials_is_not_wired_at_all(keys):
    """The 20-second defect.

    Wiring it anyway looks harmless — the router skips unavailable providers —
    but the skip happens *after* the gatekeeper has retried the missing key
    three times, five seconds apart, per vendor. That is most of the turn
    deadline spent proving a key is still absent.
    """
    keys()
    manager = Manager(**{"llm.primary": "anthropic", "llm.fallback": "deepseek"})

    assert names(build_speaker(manager, Bus())) == ["template"]


def test_a_skipped_vendor_says_so_rather_than_vanishing(keys):
    """Silence here would read as "no vendor was configured", which is a
    different problem from "the key is missing" and has a different fix."""
    keys()
    bus = Bus()

    paid_provider("anthropic", Manager(), bus)

    skipped = [event for event in bus.events if event["event"] == "llm.provider_skipped"]
    assert skipped and "ANTHROPIC_API_KEY" in skipped[0]["reason"]


def test_an_unknown_provider_name_is_ignored(keys):
    keys(ANTHROPIC_API_KEY="k")

    assert paid_provider("hal9000", Manager(), Bus()) is None


def test_the_meter_carries_the_agreed_series_cap():
    """The series budget is an agreed term — exceeding it is a breach."""
    meter = token_meter(Manager(**{"llm.series_token_budget": 200_000}), Bus())

    assert meter.series.limit == 200_000


def test_the_router_and_the_meter_are_the_same_object(keys):
    """One counter, so the dashboard and the emailed report cannot disagree
    about how close to the cap we are."""
    keys()
    meter = token_meter(Manager(), Bus())

    speaker = build_speaker(Manager(), Bus(), meter)

    assert speaker._router.meter is meter


def test_tokens_recorded_by_the_router_reach_the_meter(keys):
    """The chain the report depends on: router records, meter totals per
    sub-game, `MatchRunner` reads it into the game record, and the filer sums
    those into `tokens_total_series`. Every link was intact except the wiring.
    """
    from najamjad_agent.llm.base import Completion, Usage

    keys()
    meter = token_meter(Manager(), Bus())
    speaker = build_speaker(Manager(), Bus(), meter)

    meter.record(Usage(input_tokens=120, output_tokens=30), model="m", purpose="hint", sub_game=2)

    assert speaker._router.meter is meter
    assert meter.per_sub_game[2] == 150
    assert meter.series.spent == 150
    assert isinstance(Completion, type)


def test_the_match_record_reports_what_the_sub_game_cost():
    """`MatchRunner._tokens_for` is what puts a real number in the report.

    The field was read by the report builder and never written by the match, so
    every token figure we emailed was 0 — true only while play was
    template-only, and silently false the moment a vendor is wired.
    """
    from najamjad_agent.domain.match import MatchRunner

    class Meter:
        per_sub_game = {1: 640}

    runner = MatchRunner.__new__(MatchRunner)
    runner._meter = Meter()

    assert runner._tokens_for(1) == 640
    assert runner._tokens_for(9) == 0, "a game with no spend is zero, not an error"


def test_no_meter_is_zero_rather_than_a_crash():
    """A config-only run has no meter and must not explode building a record."""
    from najamjad_agent.domain.match import MatchRunner

    runner = MatchRunner.__new__(MatchRunner)
    runner._meter = None

    assert runner._tokens_for(1) == 0
