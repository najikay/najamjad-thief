"""Tests for the fixed score table, series aggregation, and the tie rule."""

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.scoring import ScoreTable, aggregate_series

GROUPS = ("najamjad", "rival-team")
SCORING = {
    "scoring": {
        "capture_cop": 20,
        "capture_thief": 5,
        "survival_cop": 5,
        "survival_thief": 10,
        "tie_score": 2,
    }
}


@pytest.fixture()
def table() -> ScoreTable:
    return ScoreTable.from_config(SCORING)


def test_capture_scores_match_appendix_f(table: ScoreTable) -> None:
    assert table.score_subgame(EndReason.CAPTURE) == {Role.COP: 20, Role.THIEF: 5}


def test_survival_scores_match_appendix_f(table: ScoreTable) -> None:
    assert table.score_subgame(EndReason.SURVIVAL) == {Role.COP: 5, Role.THIEF: 10}


@pytest.mark.parametrize(
    "reason",
    [EndReason.TIMEOUT, EndReason.TAMPER_FORFEIT, EndReason.OPPONENT_QUIT, EndReason.STOPPED],
)
def test_technical_endings_score_zero_for_both(table: ScoreTable, reason: EndReason) -> None:
    """A technical loss zeroes both sides, so nobody profits from a dead protocol."""
    assert table.score_subgame(reason) == {Role.COP: 0, Role.THIEF: 0}


@pytest.mark.parametrize("key", list(SCORING["scoring"]))
def test_deviating_score_values_are_rejected(key: str) -> None:
    config = {"scoring": {**SCORING["scoring"], key: 99}}
    with pytest.raises(ValueError, match=key):
        ScoreTable.from_config(config)


def test_series_totals_and_wins_accumulate() -> None:
    sub_games = [
        {"najamjad": 20, "rival-team": 5},
        {"najamjad": 10, "rival-team": 5},
        {"najamjad": 5, "rival-team": 10},
    ]
    result = aggregate_series(sub_games, GROUPS, tie_score=2)
    assert result.total_score == {"najamjad": 35, "rival-team": 20}
    assert result.sub_games_won == {"najamjad": 2, "rival-team": 1}
    assert result.winner_group == "najamjad"
    assert result.series_tie is False
    assert result.tie_award is None


def test_six_mini_game_series_aggregates() -> None:
    """A league series is 6 mini-games (Appendix F Table 18, fixed)."""
    sub_games = [{"najamjad": 20, "rival-team": 5}] * 6
    result = aggregate_series(sub_games, GROUPS, tie_score=2)
    assert result.total_score == {"najamjad": 120, "rival-team": 30}
    assert result.sub_games_won["najamjad"] == 6


def test_equal_series_totals_award_the_tie_score_to_both() -> None:
    sub_games = [{"najamjad": 20, "rival-team": 5}, {"najamjad": 5, "rival-team": 20}]
    result = aggregate_series(sub_games, GROUPS, tie_score=2)
    assert result.series_tie is True
    assert result.winner_group is None, "golden report expects null winner on a tie"
    assert result.tie_award == 2
    assert result.total_score == {"najamjad": 25, "rival-team": 25}, "true totals preserved"


def test_drawn_mini_game_counts_as_a_tie_not_a_win() -> None:
    result = aggregate_series([{"najamjad": 0, "rival-team": 0}], GROUPS, tie_score=2)
    assert result.ties == 1
    assert result.sub_games_won == {"najamjad": 0, "rival-team": 0}
