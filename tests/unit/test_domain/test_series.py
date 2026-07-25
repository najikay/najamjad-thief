"""Tests for series bookkeeping: role alternation, scoring, tie rule."""

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import (
    MINI_GAMES_PER_SERIES,
    SeriesTracker,
    role_for,
)

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
def tracker() -> SeriesTracker:
    return SeriesTracker(
        our_group="najamjad",
        their_group="rival",
        table=ScoreTable.from_config(SCORING),
        first_role=Role.COP,
    )


def test_series_is_six_mini_games() -> None:
    """Appendix F Table 18: fixed at 6, not the reference default of 1."""
    assert MINI_GAMES_PER_SERIES == 6


def test_roles_alternate_every_mini_game() -> None:
    roles = [role_for(number, Role.COP) for number in range(1, 7)]
    assert roles == [Role.COP, Role.THIEF, Role.COP, Role.THIEF, Role.COP, Role.THIEF]


def test_role_alternation_respects_the_starting_side() -> None:
    assert role_for(1, Role.THIEF) is Role.THIEF
    assert role_for(2, Role.THIEF) is Role.COP


def test_each_side_plays_both_roles_equally_over_a_series() -> None:
    roles = [role_for(number, Role.COP) for number in range(1, MINI_GAMES_PER_SERIES + 1)]
    assert roles.count(Role.COP) == roles.count(Role.THIEF) == 3


def test_sub_game_numbering_starts_at_one() -> None:
    with pytest.raises(ValueError, match="starts at 1"):
        role_for(0, Role.COP)


def test_tracker_reports_the_next_sub_game_and_role(tracker: SeriesTracker) -> None:
    assert tracker.next_sub_game == 1
    assert tracker.next_role() is Role.COP
    tracker.record(EndReason.CAPTURE, Role.COP)
    assert tracker.next_sub_game == 2
    assert tracker.next_role() is Role.THIEF


def test_capture_as_cop_scores_twenty_five_split(tracker: SeriesTracker) -> None:
    outcome = tracker.record(EndReason.CAPTURE, Role.COP)
    assert (outcome.our_score, outcome.their_score) == (20, 5)


def test_capture_as_thief_scores_the_thief_side(tracker: SeriesTracker) -> None:
    outcome = tracker.record(EndReason.CAPTURE, Role.THIEF)
    assert (outcome.our_score, outcome.their_score) == (5, 20)


def test_survival_as_thief_scores_ten(tracker: SeriesTracker) -> None:
    outcome = tracker.record(EndReason.SURVIVAL, Role.THIEF)
    assert (outcome.our_score, outcome.their_score) == (10, 5)


def test_failed_audit_overrides_the_board_result(tracker: SeriesTracker) -> None:
    """Rule 19: a tampered game is void whatever happened on the board."""
    outcome = tracker.record(EndReason.CAPTURE, Role.COP, audit_passed=False)
    assert outcome.end_reason is EndReason.TAMPER_FORFEIT
    assert (outcome.our_score, outcome.their_score) == (0, 0)


def test_series_completes_after_six_games(tracker: SeriesTracker) -> None:
    for number in range(MINI_GAMES_PER_SERIES):
        assert not tracker.is_complete
        tracker.record(EndReason.CAPTURE, role_for(number + 1, Role.COP))
    assert tracker.is_complete


def test_series_result_aggregates_alternating_roles(tracker: SeriesTracker) -> None:
    for number in range(MINI_GAMES_PER_SERIES):
        tracker.record(EndReason.CAPTURE, role_for(number + 1, Role.COP))
    result = tracker.result()
    assert result.total_score == {"najamjad": 75, "rival": 75}
    assert result.series_tie is True
    assert result.winner_group is None
    assert result.tie_award == 2


def test_dominant_series_names_a_winner(tracker: SeriesTracker) -> None:
    tracker.record(EndReason.CAPTURE, Role.COP)
    tracker.record(EndReason.SURVIVAL, Role.THIEF)
    result = tracker.result()
    assert result.total_score == {"najamjad": 30, "rival": 10}
    assert result.winner_group == "najamjad"
    assert result.series_tie is False


def test_outcomes_record_steps_for_the_report(tracker: SeriesTracker) -> None:
    outcome = tracker.record(EndReason.SURVIVAL, Role.THIEF, steps=35)
    assert outcome.steps == 35
    assert outcome.sub_game == 1
