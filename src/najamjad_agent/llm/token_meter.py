"""Token metering — primarily a reporting obligation, not a cost control.

The grade is a league ranking, so **match quality always outranks token
thrift**. This module exists because the book requires us to meter consumption
and report it (rule 54), and the guidelines require a cost table (§11). It is
not here to make the agent play worse to save money.

That said, the agreed per-series cap (~200k, negotiable — Appendix F Table 18)
is a *term we sign*, so exceeding it would be a rule breach rather than merely
an expense. The thresholds below protect that agreement:

* **warn** at 70% — visibility only, nothing changes;
* **degrade** at 90% — fall back to the zero-token provider so play continues
  legally rather than stopping;
* **stop** at 100% — no further paid calls in that scope.

In practice none of these can bind. Measured usage is **2.3% of the series cap**
— 4,577 tokens for a six-game series, or 6.8% in the worst case where every game
runs the full survival horizon (`docs/TOKEN_BUDGET.md`, measured by
`scripts/measure_tokens.py`). The safety net exists for a runaway loop, not for
normal play. The project ceiling is set generously for the same reason — it
should never be the thing that decides a match.
"""

from dataclasses import dataclass, field
from typing import Any

from ..shared.events import Emit

WARN_RATIO = 0.70
DEGRADE_RATIO = 0.90


@dataclass(frozen=True)
class Usage:
    """Tokens consumed by one call, split as the cost table requires."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        """Combined tokens, the figure reported to the lecturer."""
        return self.input_tokens + self.output_tokens


@dataclass
class BudgetState:
    """Consumption and headroom for one scope (series or project)."""

    limit: int
    spent: int = 0

    @property
    def remaining(self) -> int:
        """Tokens still available (never negative)."""
        return max(0, self.limit - self.spent)

    @property
    def ratio(self) -> float:
        """Fraction of the budget consumed."""
        return 1.0 if self.limit <= 0 else min(1.0, self.spent / self.limit)

    @property
    def exhausted(self) -> bool:
        """True once no paid call may be made in this scope."""
        return self.spent >= self.limit

    @property
    def should_degrade(self) -> bool:
        """True once we switch to the zero-token provider to keep playing."""
        return self.ratio >= DEGRADE_RATIO


@dataclass
class TokenMeter:
    """Records usage against series and project budgets."""

    # Series cap = the agreed term. Project ceiling is deliberately ~10x our
    # measured need: it is a runaway-loop backstop, never a reason to play worse.
    series_limit: int = 200_000
    project_limit: int = 5_000_000
    emit: Emit | None = None
    by_purpose: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, int] = field(default_factory=dict)
    per_sub_game: dict[int, int] = field(default_factory=dict)
    series: BudgetState = field(init=False)
    project: BudgetState = field(init=False)
    _warned: set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        """Open both budget scopes."""
        self.series = BudgetState(limit=self.series_limit)
        self.project = BudgetState(limit=self.project_limit)

    def record(
        self,
        usage: Usage,
        model: str,
        purpose: str = "hint",
        sub_game: int = 0,
    ) -> Usage:
        """Fold one call's usage into every scope and breakdown."""
        total = usage.total
        self.series.spent += total
        self.project.spent += total
        self.by_purpose[purpose] = self.by_purpose.get(purpose, 0) + total
        self.by_model[model] = self.by_model.get(model, 0) + total
        self.per_sub_game[sub_game] = self.per_sub_game.get(sub_game, 0) + total
        self._event(
            "tokens.recorded",
            model=model,
            purpose=purpose,
            sub_game=sub_game,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            series_remaining=self.series.remaining,
        )
        self._check_thresholds()
        return usage

    def may_spend(self, estimated: int = 0) -> bool:
        """Whether a paid call is still allowed in both scopes."""
        if self.series.exhausted or self.project.exhausted:
            return False
        return self.series.remaining >= estimated or estimated == 0

    def start_series(self, limit: int | None = None) -> None:
        """Reset the per-series scope for a new opponent."""
        self.series = BudgetState(limit=limit if limit is not None else self.series_limit)
        self.per_sub_game.clear()
        self._warned.discard("series")
        self._event("tokens.series_started", limit=self.series.limit)

    def report(self) -> dict[str, Any]:
        """The consumption block for the result email and the cost table."""
        return {
            "series_total": self.series.spent,
            "series_limit": self.series.limit,
            "project_total": self.project.spent,
            "project_limit": self.project.limit,
            "by_purpose": dict(self.by_purpose),
            "by_model": dict(self.by_model),
            "per_sub_game": {str(key): value for key, value in sorted(self.per_sub_game.items())},
        }

    def _check_thresholds(self) -> None:
        """Warn once per scope, then announce degradation and exhaustion."""
        for name, state in (("series", self.series), ("project", self.project)):
            if state.ratio >= WARN_RATIO and name not in self._warned:
                self._warned.add(name)
                self._event(
                    "tokens.budget_warning",
                    scope=name,
                    spent=state.spent,
                    limit=state.limit,
                    ratio=round(state.ratio, 3),
                )
            if state.should_degrade:
                self._event("tokens.degrade", scope=name, remaining=state.remaining)
            if state.exhausted:
                self._event("tokens.exhausted", scope=name, limit=state.limit)

    def _event(self, name: str, **fields: Any) -> None:
        if self.emit is not None:
            self.emit({"event": name, **fields})
