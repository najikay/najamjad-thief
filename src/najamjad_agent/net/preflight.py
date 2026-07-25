"""Preflight — prove the agent is match-ready before anything counts.

Every check here maps to a way Assignment 6 lost time in the field: a tunnel
that was not reachable, a Gmail token that needed interactive consent nobody
could give, an LLM key that had quietly stopped working, config that did not
match the opponent's. Each was discovered *during* a match. This turns all of
them into a red line on a checklist beforehand.

Checks never raise: a failing check reports itself so the operator sees the
whole picture in one run, rather than fixing one problem at a time.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

OK = "ok"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Outcome of a single preflight check."""

    name: str
    status: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        """A skipped check is not a failure — it is simply not applicable."""
        return self.status in (OK, SKIPPED)

    @property
    def symbol(self) -> str:
        """Console marker for the checklist."""
        return {OK: "PASS", FAILED: "FAIL", SKIPPED: "SKIP"}[self.status]


@dataclass
class PreflightReport:
    """The full checklist and its verdict."""

    results: list[CheckResult] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """True only when nothing is red."""
        return all(result.passed for result in self.results)

    @property
    def exit_code(self) -> int:
        """Process exit code: nonzero if the agent is not match-ready."""
        return 0 if self.ready else 1

    @property
    def failures(self) -> list[CheckResult]:
        """Just the red lines, for the operator alert."""
        return [result for result in self.results if not result.passed]

    def render(self) -> str:
        """The human-readable checklist."""
        lines = [f"[{result.symbol}] {result.name}: {result.detail}" for result in self.results]
        verdict = "READY" if self.ready else f"NOT READY ({len(self.failures)} blocking)"
        lines.append(f"preflight: {verdict}")
        return "\n".join(lines)


def run_check(name: str, probe: Callable[[], Any]) -> CheckResult:
    """Run one probe, converting any failure into a red line.

    A probe returns a detail string on success, raises to fail, or returns None
    to mark itself not-applicable.
    """
    try:
        detail = probe()
    except Exception as error:  # noqa: BLE001 - a check must never abort the run
        return CheckResult(name, FAILED, f"{type(error).__name__}: {error}")
    if detail is None:
        return CheckResult(name, SKIPPED, "not applicable")
    return CheckResult(name, OK, str(detail))


def run_preflight(checks: dict[str, Callable[[], Any]]) -> PreflightReport:
    """Run every named check and collect the checklist."""
    return PreflightReport([run_check(name, probe) for name, probe in checks.items()])


def check_tunnel_self_call(public_url: str, call: Callable[[str], Any]) -> Callable[[], str]:
    """Verify our own MCP server answers through the PUBLIC url, not localhost.

    Calling ourselves locally proves nothing: the failure we care about is the
    tunnel, DNS, or firewall between an opponent and us.
    """

    def probe() -> str:
        response = call(public_url)
        if not response:
            raise RuntimeError(f"no response from {public_url}")
        return f"reachable at {public_url}"

    return probe


def check_clock_skew(local_now: Callable[[], float], reference_now: Callable[[], float], tolerance: float = 120.0) -> Callable[[], str]:
    """Guard against a clock so skewed that deadlines misfire."""

    def probe() -> str:
        skew = abs(local_now() - reference_now())
        if skew > tolerance:
            raise RuntimeError(f"clock skew {skew:.1f}s exceeds tolerance {tolerance:.0f}s")
        return f"skew {skew:.1f}s within tolerance"

    return probe


def check_token_budget(meter: Any, minimum_ratio: float = 0.10) -> Callable[[], str]:
    """Refuse to start a match with too little budget left to finish it."""

    def probe() -> str:
        remaining = meter.series.remaining
        if not meter.may_spend():
            raise RuntimeError("token budget exhausted; a match would run template-only")
        if meter.series.limit and remaining < meter.series.limit * minimum_ratio:
            raise RuntimeError(f"only {remaining} tokens left of {meter.series.limit}")
        return f"{remaining} of {meter.series.limit} tokens available"

    return probe
