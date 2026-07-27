"""The token-cost table (T-2220) and the savings analysis (T-2221).

The risk with a cost table is not arithmetic, it is framing: a number that is
measured sitting next to one that is assumed, with nothing to tell them apart.
These tests pin the arithmetic and the honesty of the labels.
"""

import pytest

from najamjad_agent.analysis.costs import (
    GAMES_PER_SERIES,
    SURVIVAL_STEPS,
    as_markdown,
    cost_rows,
    headline,
    worst_case,
)

CENSUS = {
    "model": "claude-haiku-4-5-20251001",
    "series_token_budget": 200_000,
    "steps_per_game": [10] * 6,
    "prices_usd_per_million": {"claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0}},
    "measurements": [
        {"every_n_steps": 2, "calls": 30, "input_tokens": 2_000, "output_tokens": 1_000,
         "total_tokens": 3_000},
        {"every_n_steps": 1, "calls": 60, "input_tokens": 4_000, "output_tokens": 2_000,
         "total_tokens": 6_000},
    ],
}


def test_rows_come_back_in_cadence_order_however_they_were_measured():
    """The census is written in the order the sweeps ran, not a readable one."""
    assert [row.cadence for row in cost_rows(CENSUS)] == [1, 2]


def test_cost_is_the_split_rate_not_a_blended_one():
    """Output tokens cost 5x input here; averaging the two understates the bill."""
    every_turn = cost_rows(CENSUS)[0]

    # 4000/1e6*$1 + 2000/1e6*$5 = $0.004 + $0.010
    assert every_turn.usd == pytest.approx(0.014)


def test_savings_are_measured_against_calling_the_model_every_turn():
    rows = {row.cadence: row for row in cost_rows(CENSUS)}

    assert rows[1].saving_vs_all_llm == pytest.approx(0.0), "the baseline saves nothing"
    assert rows[2].saving_vs_all_llm == pytest.approx(0.5)
    assert rows[2].budget_share == pytest.approx(0.015)


def test_the_worst_case_scales_to_a_series_that_never_ends_early():
    """Our cop wins fast, so the measured series flatters the budget."""
    ceiling = worst_case(CENSUS, cadence=2)

    assert ceiling["turns"] == SURVIVAL_STEPS * GAMES_PER_SERIES
    assert ceiling["scale"] == pytest.approx(210 / 60)
    assert ceiling["tokens"] == round(3_000 * 210 / 60)
    assert ceiling["budget_share"] > cost_rows(CENSUS)[1].budget_share


def test_the_shipped_cadence_is_marked_in_the_table():
    """A reader must not have to cross-reference the config to find our setting."""
    table = as_markdown(cost_rows(CENSUS), shipped=2)

    shipped = [line for line in table.splitlines() if "(shipped)" in line]
    assert len(shipped) == 1
    assert "every 2 turns" in shipped[0]


def test_the_table_is_valid_markdown_with_one_row_per_cadence():
    table = as_markdown(cost_rows(CENSUS), shipped=2)
    lines = table.splitlines()

    assert lines[1].startswith("|---")
    assert len(lines) == 2 + len(CENSUS["measurements"])
    assert all(line.count("|") == 9 for line in lines), "ragged rows break the render"


def test_the_headline_quotes_the_budget_share_and_the_saving():
    """It is written to be pasted into the report without an editor."""
    sentence = headline(CENSUS, shipped=2)

    assert "3,000 tokens" in sentence
    assert "1.5%" in sentence and "50%" in sentence
    assert "35-step" in sentence


def test_the_real_census_is_a_small_fraction_of_the_agreed_cap():
    """The claim the report makes; if it ever stops holding, this fails first."""
    from najamjad_agent.analysis.datasets import load_tokens

    census = load_tokens()
    shipped = {row.cadence: row for row in cost_rows(census)}[2]

    assert shipped.budget_share < 0.10, "cost has become a real constraint — re-read §6"
    assert worst_case(census, 2)["budget_share"] < 0.25
