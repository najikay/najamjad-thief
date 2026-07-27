"""Seeded self-play through the real match machinery.

Two things are checked, and the first matters more than the second.

**Correctness**: across every seeded game the two peers must agree on how each
one ended. Three separate defects were found this way — a captured thief that
never answered, a survival nobody announced, and a barrier capture only the cop
noticed — and each would have voided games under rules 33-35 while every unit
test stayed green.

**Competitiveness**: our brains must beat the obvious strategy. The floors here
sit well below measured performance, because this is a regression alarm rather
than a benchmark; the real numbers live in `scripts/self_play.py`.
"""

import pytest

from scripts.self_play import run

GAMES = 8
SEED = 7


@pytest.fixture(scope="module")
def summary() -> dict:
    """One seeded sweep, shared by every assertion in this module."""
    return run(games=GAMES, seed=SEED, out=None)


@pytest.mark.slow
@pytest.mark.parametrize(
    "matchup", ["ours_cop_vs_greedy_thief", "ours_thief_vs_greedy_cop", "greedy_vs_greedy"]
)
def test_the_two_peers_never_disagree_about_how_a_game_ended(summary, matchup):
    """Contradictory reports void the game for both sides (rules 33-35)."""
    assert summary[matchup]["disagreements"] == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "matchup", ["ours_cop_vs_greedy_thief", "ours_thief_vs_greedy_cop", "greedy_vs_greedy"]
)
def test_every_game_audits_clean_and_none_stall(summary, matchup):
    assert summary[matchup]["audit_failures"] == 0
    assert summary[matchup]["stalled"] == 0
    assert summary[matchup]["played"] > 0, "a sweep that played nothing proves nothing"


@pytest.mark.slow
def test_our_cop_catches_the_greedy_thief_far_more_often_than_greedy_does(summary):
    """The claim the league actually rewards."""
    ours = summary["ours_cop_vs_greedy_thief"]["capture_rate"]
    baseline = summary["greedy_vs_greedy"]["capture_rate"]

    assert ours >= 0.80, f"cop capture rate fell to {ours}"
    assert ours > baseline, "our cop must beat the obvious strategy, not match it"


@pytest.mark.slow
def test_our_thief_survives_the_greedy_cop_almost_always(summary):
    caught = summary["ours_thief_vs_greedy_cop"]["capture_rate"]

    assert caught <= 0.20, f"our thief is being caught {caught:.0%} of the time"
