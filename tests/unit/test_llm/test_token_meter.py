"""Tests for token metering, budget thresholds, and the reported breakdown."""

import pytest

from najamjad_agent.llm.token_meter import TokenMeter, Usage


@pytest.fixture()
def events() -> list[dict]:
    return []


@pytest.fixture()
def meter(events: list[dict]) -> TokenMeter:
    return TokenMeter(series_limit=1000, project_limit=5000, emit=events.append)


def test_usage_totals_input_and_output() -> None:
    assert Usage(input_tokens=120, output_tokens=30).total == 150


def test_default_series_limit_matches_the_book() -> None:
    """Appendix F Table 18: ~200,000 tokens per series (negotiable)."""
    assert TokenMeter().series_limit == 200_000


def test_recording_reduces_remaining_in_both_scopes(meter: TokenMeter) -> None:
    meter.record(Usage(100, 50), model="haiku", purpose="hint", sub_game=1)
    assert meter.series.spent == 150
    assert meter.project.spent == 150
    assert meter.series.remaining == 850


def test_breakdown_is_kept_by_purpose_model_and_game(meter: TokenMeter) -> None:
    """The cost table needs real measured numbers, not one lump sum."""
    meter.record(Usage(80, 20), model="haiku", purpose="hint", sub_game=1)
    meter.record(Usage(200, 60), model="sonnet", purpose="negotiation", sub_game=0)
    meter.record(Usage(40, 10), model="haiku", purpose="hint", sub_game=2)
    report = meter.report()
    assert report["by_purpose"] == {"hint": 150, "negotiation": 260}
    assert report["by_model"] == {"haiku": 150, "sonnet": 260}
    assert report["per_sub_game"] == {"0": 260, "1": 100, "2": 50}


def test_report_carries_both_budgets(meter: TokenMeter) -> None:
    meter.record(Usage(10, 10), model="haiku")
    report = meter.report()
    assert report["series_total"] == 20
    assert report["series_limit"] == 1000
    assert report["project_limit"] == 5000


def test_a_warning_fires_at_seventy_percent(meter: TokenMeter, events: list[dict]) -> None:
    """Early enough that the operator can still act on it."""
    meter.record(Usage(700, 0), model="haiku")
    warnings = [event for event in events if event["event"] == "tokens.budget_warning"]
    assert warnings and warnings[0]["scope"] == "series"


def test_the_warning_fires_only_once_per_scope(meter: TokenMeter, events: list[dict]) -> None:
    for _ in range(3):
        meter.record(Usage(250, 0), model="haiku")
    warnings = [e for e in events if e["event"] == "tokens.budget_warning" and e["scope"] == "series"]
    assert len(warnings) == 1


def test_degradation_is_announced_at_ninety_percent(meter: TokenMeter, events: list[dict]) -> None:
    """We drop to the zero-token provider rather than stop playing."""
    meter.record(Usage(900, 0), model="haiku")
    assert meter.series.should_degrade
    assert any(event["event"] == "tokens.degrade" for event in events)


def test_below_ninety_percent_does_not_degrade(meter: TokenMeter) -> None:
    meter.record(Usage(800, 0), model="haiku")
    assert not meter.series.should_degrade


def test_spending_is_refused_once_the_series_budget_is_gone(meter: TokenMeter) -> None:
    meter.record(Usage(1000, 0), model="haiku")
    assert meter.series.exhausted
    assert not meter.may_spend()


def test_exhaustion_is_announced(meter: TokenMeter, events: list[dict]) -> None:
    meter.record(Usage(1000, 0), model="haiku")
    exhausted = [event for event in events if event["event"] == "tokens.exhausted"]
    assert exhausted and exhausted[0]["scope"] == "series"


def test_the_project_budget_stops_spending_even_with_series_headroom() -> None:
    """A fresh series must not be able to overspend the project as a whole."""
    meter = TokenMeter(series_limit=1000, project_limit=1200)
    meter.record(Usage(1000, 0), model="haiku")
    meter.start_series()
    assert meter.series.remaining == 1000
    meter.record(Usage(200, 0), model="haiku")
    assert meter.project.exhausted
    assert not meter.may_spend()


def test_may_spend_respects_an_estimate(meter: TokenMeter) -> None:
    meter.record(Usage(950, 0), model="haiku")
    assert meter.may_spend(estimated=10)
    assert not meter.may_spend(estimated=500)


def test_starting_a_series_resets_only_the_series_scope(meter: TokenMeter) -> None:
    meter.record(Usage(400, 0), model="haiku", sub_game=1)
    meter.start_series()
    assert meter.series.spent == 0
    assert meter.project.spent == 400, "project spend accumulates across opponents"
    assert meter.per_sub_game == {}


def test_a_negotiated_series_cap_can_be_applied(meter: TokenMeter) -> None:
    """The per-series budget is a negotiable term (Appendix F Table 18)."""
    meter.start_series(limit=50_000)
    assert meter.series.limit == 50_000


def test_recording_emits_running_headroom(meter: TokenMeter, events: list[dict]) -> None:
    meter.record(Usage(100, 0), model="haiku", purpose="hint", sub_game=3)
    recorded = [event for event in events if event["event"] == "tokens.recorded"][0]
    assert recorded["series_remaining"] == 900
    assert recorded["purpose"] == "hint"
    assert recorded["sub_game"] == 3


def test_a_zero_limit_scope_is_treated_as_exhausted() -> None:
    """Template-only mode: no paid call is ever permitted."""
    meter = TokenMeter(series_limit=0, project_limit=0)
    assert meter.series.exhausted
    assert not meter.may_spend()
