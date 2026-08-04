"""The emailed JSON is the graded artifact, so what is in it is the deliverable.

Two defects lived in the real `result_najamjad-vs-uoh-sqak.json` that was
emailed after a real series:

1. `"tie_award": null` on a series that was not a tie — noise, but noise in the
   one file a grader reads;
2. `"ties": 3` and three sub-games marked `"tie": true` whose `"result"` was
   `"timeout"`. **Nobody drew those games; they never finished.** A technical
   ending scores 0/0 for both sides, equal scores are how a tie is detected, and
   so every abandoned mini-game was filed as a draw. That is our own report
   misdescribing our own match, which is exactly what rules 33-35 void a report
   for when the opponent's copy says something else.
"""

import json

from najamjad_agent.constants import EndReason, is_technical
from najamjad_agent.domain.scoring import aggregate_series
from najamjad_agent.reporting.artifacts import OMIT_WHEN_NULL, _without_absent

GROUPS = ("najamjad", "uoh-sqak")

#: The real series, as it was actually scored and emailed.
REAL_SERIES = [
    {"najamjad": 0, "uoh-sqak": 0, "end_reason": "timeout"},
    {"najamjad": 5, "uoh-sqak": 20, "end_reason": "capture"},
    {"najamjad": 0, "uoh-sqak": 0, "end_reason": "timeout"},
    {"najamjad": 5, "uoh-sqak": 20, "end_reason": "capture"},
    {"najamjad": 0, "uoh-sqak": 0, "end_reason": "timeout"},
    {"najamjad": 5, "uoh-sqak": 20, "end_reason": "capture"},
]


def test_an_abandoned_game_is_not_a_draw() -> None:
    """The defect, replayed on the real numbers. It reported three draws."""
    result = aggregate_series(REAL_SERIES, GROUPS, tie_score=2)

    assert result.ties == 0
    assert result.technical == 3


def test_the_scores_themselves_are_unchanged() -> None:
    """Only the description was wrong; the points were always right."""
    result = aggregate_series(REAL_SERIES, GROUPS, tie_score=2)

    assert result.total_score == {"najamjad": 15, "uoh-sqak": 60}
    assert result.winner_group == "uoh-sqak"


def test_a_genuine_draw_is_still_counted_as_one() -> None:
    """The fix must not swing the other way and hide real ties."""
    drawn = [{"najamjad": 5, "uoh-sqak": 5, "end_reason": "survival"}]

    result = aggregate_series(drawn, GROUPS, tie_score=2)

    assert result.ties == 1
    assert result.technical == 0


def test_every_technical_ending_is_recognised() -> None:
    """A verdict missing from the list silently becomes a draw again."""
    for reason in (
        EndReason.TIMEOUT,
        EndReason.TAMPER_FORFEIT,
        EndReason.OPPONENT_QUIT,
        EndReason.STOPPED,
    ):
        assert is_technical(reason.value), f"{reason.value} would be filed as a draw"


def test_a_played_ending_is_never_technical() -> None:
    assert not is_technical(EndReason.CAPTURE.value)
    assert not is_technical(EndReason.SURVIVAL.value)
    assert not is_technical("")
    assert not is_technical(None)


def test_a_null_tie_award_is_dropped_from_the_file() -> None:
    """It appeared in every emitted result, including non-ties."""
    cleaned = _without_absent({"series_tie": False, "tie_award": None, "ties": 0})

    assert "tie_award" not in cleaned
    assert cleaned["series_tie"] is False


def test_a_meaningful_null_survives() -> None:
    """`winner_group: null` is the report's own way of saying a game was drawn.

    Dropping it would turn a stated draw into a missing field, which is a
    different claim and one the opponent's copy would contradict.
    """
    cleaned = _without_absent({"winner_group": None, "sub_game_number": 1})

    assert "winner_group" in cleaned
    assert cleaned["winner_group"] is None


def test_a_set_tie_award_is_kept() -> None:
    """On a real tie the award is the whole point of the field."""
    cleaned = _without_absent({"series_tie": True, "tie_award": 2})

    assert cleaned["tie_award"] == 2


def test_pruning_reaches_nested_sub_games() -> None:
    """The sub-game rows are where most of the file lives."""
    cleaned = _without_absent(
        {"sub_games": [{"tie_award": None, "winner_group": None, "sub_game_number": 1}]}
    )

    assert "tie_award" not in cleaned["sub_games"][0]
    assert "winner_group" in cleaned["sub_games"][0]


def test_the_omit_list_is_explicit_rather_than_a_blanket_rule() -> None:
    """A blanket `exclude_none` would take `winner_group` with it."""
    assert "winner_group" not in OMIT_WHEN_NULL
    assert "tie_award" in OMIT_WHEN_NULL


def test_pruning_leaves_ordinary_values_alone() -> None:
    payload = {"a": 1, "b": "x", "c": [1, 2], "d": {"e": False}, "f": 0}

    assert _without_absent(payload) == payload


def test_the_result_is_still_serialisable() -> None:
    """Whatever we prune, the file has to remain valid JSON."""
    cleaned = _without_absent({"tie_award": None, "sub_games": [{"winner_group": None}]})

    assert json.loads(json.dumps(cleaned)) == cleaned
