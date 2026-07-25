"""Tests for the preflight checklist — the match-day readiness gate."""

import pytest

from najamjad_agent.llm.token_meter import TokenMeter, Usage
from najamjad_agent.net.preflight import (
    CheckResult,
    check_clock_skew,
    check_token_budget,
    check_tunnel_self_call,
    run_check,
    run_preflight,
)


def test_a_passing_probe_is_green() -> None:
    result = run_check("tunnel", lambda: "reachable")
    assert result.status == "ok"
    assert result.passed
    assert result.detail == "reachable"


def test_a_raising_probe_becomes_a_red_line_not_a_crash() -> None:
    """One broken check must not hide the state of all the others."""

    def broken() -> str:
        raise ConnectionError("tunnel down")

    result = run_check("tunnel", broken)
    assert result.status == "failed"
    assert not result.passed
    assert "ConnectionError" in result.detail


def test_a_probe_returning_none_is_skipped_not_failed() -> None:
    result = run_check("contract", lambda: None)
    assert result.status == "skipped"
    assert result.passed, "not applicable is not a failure"


def test_every_check_runs_even_after_one_fails() -> None:
    ran: list[str] = []

    def failing() -> str:
        ran.append("first")
        raise RuntimeError("nope")

    def passing() -> str:
        ran.append("second")
        return "fine"

    report = run_preflight({"first": failing, "second": passing})
    assert ran == ["first", "second"]
    assert len(report.results) == 2


def test_the_report_is_red_when_anything_fails() -> None:
    report = run_preflight({"a": lambda: "fine", "b": lambda: 1 / 0})
    assert not report.ready
    assert report.exit_code == 1
    assert [failure.name for failure in report.failures] == ["b"]


def test_the_report_is_green_when_everything_passes() -> None:
    report = run_preflight({"a": lambda: "fine", "b": lambda: None})
    assert report.ready
    assert report.exit_code == 0
    assert report.failures == []


def test_the_rendered_checklist_names_each_check() -> None:
    report = run_preflight({"tunnel": lambda: "up", "gmail": lambda: 1 / 0})
    rendered = report.render()
    assert "[PASS] tunnel: up" in rendered
    assert "[FAIL] gmail" in rendered
    assert "NOT READY (1 blocking)" in rendered


def test_a_fully_green_run_says_ready() -> None:
    assert "preflight: READY" in run_preflight({"a": lambda: "ok"}).render()


def test_tunnel_check_calls_the_public_url_not_localhost() -> None:
    """Calling ourselves locally proves nothing about the tunnel."""
    called: list[str] = []

    def call(url: str) -> dict:
        called.append(url)
        return {"accepted": True}

    probe = check_tunnel_self_call("https://cop.najamjad.dev/mcp", call)
    assert "reachable" in probe()
    assert called == ["https://cop.najamjad.dev/mcp"]


def test_tunnel_check_fails_on_an_empty_response() -> None:
    probe = check_tunnel_self_call("https://cop.najamjad.dev/mcp", lambda _url: None)
    with pytest.raises(RuntimeError, match="no response"):
        probe()


def test_tunnel_check_surfaces_a_connection_failure() -> None:
    def dead(_url: str):
        raise ConnectionError("connection refused")

    result = run_check("tunnel", check_tunnel_self_call("https://x/mcp", dead))
    assert result.status == "failed"


def test_clock_check_passes_within_tolerance() -> None:
    probe = check_clock_skew(lambda: 1000.0, lambda: 1030.0, tolerance=120)
    assert "within tolerance" in probe()


def test_clock_check_fails_on_large_skew() -> None:
    """A skewed clock makes deadlines fire at the wrong moment."""
    probe = check_clock_skew(lambda: 1000.0, lambda: 1400.0, tolerance=120)
    with pytest.raises(RuntimeError, match="clock skew"):
        probe()


def test_budget_check_passes_with_headroom() -> None:
    meter = TokenMeter(series_limit=1000, project_limit=5000)
    meter.record(Usage(100, 0), model="haiku")
    assert "900 of 1000" in check_token_budget(meter)()


def test_budget_check_fails_when_nearly_spent() -> None:
    """Starting a match we cannot finish wastes the opponent's time too."""
    meter = TokenMeter(series_limit=1000, project_limit=5000)
    meter.record(Usage(950, 0), model="haiku")
    with pytest.raises(RuntimeError, match="only 50 tokens left"):
        check_token_budget(meter)()


def test_budget_check_fails_when_exhausted() -> None:
    meter = TokenMeter(series_limit=100, project_limit=100)
    meter.record(Usage(100, 0), model="haiku")
    with pytest.raises(RuntimeError, match="exhausted"):
        check_token_budget(meter)()


def test_a_realistic_match_day_checklist_renders() -> None:
    """The whole point: one command, one screen, every blocker visible."""
    meter = TokenMeter(series_limit=200_000, project_limit=1_000_000)
    report = run_preflight(
        {
            "tunnel": check_tunnel_self_call("https://cop.najamjad.dev/mcp", lambda _u: {"ok": 1}),
            "clock": check_clock_skew(lambda: 100.0, lambda: 101.0),
            "tokens": check_token_budget(meter),
            "gmail-token": lambda: "token valid until 2026-08-20",
            "contract": lambda: None,
        }
    )
    assert report.ready
    assert report.render().count("[PASS]") == 4
    assert "[SKIP] contract" in report.render()


def test_check_result_symbols_are_stable() -> None:
    assert CheckResult("x", "ok").symbol == "PASS"
    assert CheckResult("x", "failed").symbol == "FAIL"
    assert CheckResult("x", "skipped").symbol == "SKIP"
