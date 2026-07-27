"""The token-cost table and the savings analysis (T-2220, T-2221).

Rendering lives here rather than in the notebook so the same table can be
dropped into `docs/TOKEN_BUDGET.md` without being retyped — a cost figure that
exists in two places in two forms is a cost figure that will disagree with
itself by submission day.

The honesty boundary is fixed by `scripts/measure_tokens.py`: call counts and
text are measured, the tokenizer is a documented proxy, the prices are the
vendor's. Nothing here re-labels an estimate as a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

SURVIVAL_STEPS = 35
GAMES_PER_SERIES = 6


@dataclass(frozen=True)
class Row:
    """One hint cadence, costed."""

    cadence: int
    calls: int
    input_tokens: int
    output_tokens: int
    total: int
    usd: float
    budget_share: float
    saving_vs_all_llm: float

    @property
    def label(self) -> str:
        """How the cadence reads in prose."""
        return "every turn" if self.cadence == 1 else f"every {self.cadence} turns"


def cost_rows(census: dict) -> list[Row]:
    """Turn a measured census into costed rows, cheapest comparison first."""
    prices = next(iter(census["prices_usd_per_million"].values()))
    budget = census["series_token_budget"]
    measurements = sorted(census["measurements"], key=lambda row: row["every_n_steps"])
    all_llm = measurements[0]["total_tokens"] if measurements else 0

    rows = []
    for entry in measurements:
        usd = (entry["input_tokens"] / 1e6 * prices["input"]
               + entry["output_tokens"] / 1e6 * prices["output"])
        rows.append(Row(
            cadence=entry["every_n_steps"],
            calls=entry["calls"],
            input_tokens=entry["input_tokens"],
            output_tokens=entry["output_tokens"],
            total=entry["total_tokens"],
            usd=round(usd, 5),
            budget_share=entry["total_tokens"] / budget if budget else 0.0,
            saving_vs_all_llm=(
                1 - entry["total_tokens"] / all_llm if all_llm else 0.0
            ),
        ))
    return rows


def worst_case(census: dict, cadence: int) -> dict:
    """Project the longest series that the rules permit.

    The measured series ends early because our cop wins fast; a six-game series
    where every game runs the full survival horizon is the real ceiling, and it
    is the number the budget must survive.
    """
    rows = {row.cadence: row for row in cost_rows(census)}
    row = rows[cadence]
    measured_turns = sum(census["steps_per_game"])
    ceiling_turns = SURVIVAL_STEPS * GAMES_PER_SERIES
    scale = ceiling_turns / measured_turns if measured_turns else 0.0
    return {
        "turns": ceiling_turns,
        "tokens": round(row.total * scale),
        "usd": round(row.usd * scale, 4),
        "budget_share": row.budget_share * scale,
        "scale": round(scale, 2),
    }


def as_markdown(rows: list[Row], shipped: int) -> str:
    """The cost table as it appears in the notebook and in the docs."""
    header = (
        "| Hint cadence | Model calls | Input tokens | Output tokens | Total | "
        "USD | Share of 200k cap | Saving vs all-LLM |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|"
    )
    lines = [header]
    for row in rows:
        mark = " **(shipped)**" if row.cadence == shipped else ""
        lines.append(
            f"| {row.label}{mark} | {row.calls} | {row.input_tokens:,} | "
            f"{row.output_tokens:,} | {row.total:,} | ${row.usd:.4f} | "
            f"{row.budget_share:.1%} | {row.saving_vs_all_llm:.0%} |"
        )
    return "\n".join(lines)


def headline(census: dict, shipped: int) -> str:
    """One sentence a reader can quote without opening the notebook."""
    rows = {row.cadence: row for row in cost_rows(census)}
    row = rows[shipped]
    ceiling = worst_case(census, shipped)
    return (
        f"A six-game series costs {row.total:,} tokens (${row.usd:.4f}) at the shipped "
        f"cadence — {row.budget_share:.1%} of the agreed {census['series_token_budget']:,} "
        f"cap, or {ceiling['budget_share']:.1%} in the worst case where every game runs "
        f"the full {SURVIVAL_STEPS}-step horizon. Skipping the model on off-cycle turns "
        f"saves {row.saving_vs_all_llm:.0%} against calling it every turn."
    )
