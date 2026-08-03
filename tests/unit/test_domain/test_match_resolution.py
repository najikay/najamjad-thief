"""Tests for the two no-play resolutions — the distinction that cost us a dispute.

The fix these lock in went in without a test. That is exactly the wrong file to
leave uncovered: it is the one place where "the peer never agreed" and "the peer
agreed and we then went silent" are told apart, and filing the second as the
first is what put our report in contradiction with uoh-sqak's.
"""

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.match_resolution import (
    resolve_abandoned,
    resolve_unplayed,
    tokens_for,
)
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker

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
        their_group="uoh-sqak",
        table=ScoreTable.from_config(SCORING),
        first_role=Role.COP,
    )


def test_an_abandoned_game_reports_the_steps_it_actually_played(tracker) -> None:
    """27 sent turns must not be filed as zero — theirs said 27 and ours said 0."""
    record = resolve_abandoned(tracker, sub_game=1, role=Role.COP, steps=27)

    assert record["steps"] == 27
    assert record["end_reason"] == EndReason.TIMEOUT.value
    assert record["audit"] == "AUDIT SKIPPED"


def test_an_abandoned_game_never_claims_it_was_never_played(tracker) -> None:
    """The wording is the dispute: rules 33-35 void both reports that disagree."""
    record = resolve_abandoned(tracker, sub_game=3, role=Role.THIEF, steps=11)

    assert "never played" not in record["audit"]
    assert record["disputed"] is False, "we went quiet; they contradicted nothing"


def test_an_abandoned_game_still_scores_the_series(tracker) -> None:
    """It consumes its mini-game — a crash must not leave the series unfinishable."""
    resolve_abandoned(tracker, sub_game=1, role=Role.COP, steps=12)

    assert tracker.next_sub_game == 2
    assert tracker.outcomes[0].steps == 12


def test_a_failed_handshake_is_unplayed_with_no_steps(tracker) -> None:
    """Nothing was exchanged, so zero is the truth here rather than a placeholder."""
    record = resolve_unplayed(tracker, sub_game=1, role=Role.COP, reason=EndReason.OPPONENT_QUIT)

    assert record["steps"] == 0
    assert record["end_reason"] == EndReason.OPPONENT_QUIT.value
    assert record["records"] == []


def test_both_resolutions_file_the_same_keys(tracker) -> None:
    """One shape downstream: a KeyError at filing time is scored as not playing."""
    abandoned = resolve_abandoned(tracker, sub_game=1, role=Role.COP, steps=9)
    unplayed = resolve_unplayed(tracker, sub_game=2, role=Role.THIEF, reason=EndReason.OPPONENT_QUIT)

    assert abandoned.keys() == unplayed.keys()


def test_neither_resolution_reveals_sealed_records(tracker) -> None:
    """No audit happened, so rule 18 keeps the nonces sealed in both shapes."""
    abandoned = resolve_abandoned(tracker, sub_game=1, role=Role.COP, steps=9)
    unplayed = resolve_unplayed(tracker, sub_game=2, role=Role.THIEF, reason=EndReason.OPPONENT_QUIT)

    assert abandoned["records"] == [] and unplayed["records"] == []


def test_tokens_come_from_the_meter_the_dashboard_reads() -> None:
    class Meter:
        per_sub_game = {2: 640}

    assert tokens_for(Meter(), 2) == 640
    assert tokens_for(Meter(), 5) == 0
    assert tokens_for(None, 2) == 0
