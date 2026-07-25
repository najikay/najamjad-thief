"""Tests for opponent profiles (interop as data) and the counted-match tracker."""

import json
from pathlib import Path

import pytest

from najamjad_agent.negotiation.adapters import (
    OpponentProfile,
    ProfileRegistry,
)
from najamjad_agent.negotiation.counted_games import (
    MAX_COUNTED_MATCHES,
    CountedGameError,
    CountedGames,
)


def test_an_unknown_opponent_gets_reference_defaults() -> None:
    """Meeting a new team is normal, not an error."""
    profile = ProfileRegistry().for_opponent("never-met-them")
    assert profile.group_id == "default"
    assert profile.tool_for("turn", "receive_turn") == "receive_turn"


def test_a_profile_can_rename_a_tool() -> None:
    profile = OpponentProfile(group_id="rival", tool_aliases={"turn": "play_turn"})
    assert profile.tool_for("turn", "receive_turn") == "play_turn"
    assert profile.tool_for("audit", "submit_audit") == "submit_audit"


def test_a_profile_can_rename_fields_in_both_directions() -> None:
    profile = OpponentProfile(group_id="rival", field_aliases={"hint": "message"})
    outgoing = profile.outgoing({"hint": "north side", "step": 1})
    assert outgoing == {"message": "north side", "step": 1}
    assert profile.incoming(outgoing) == {"hint": "north side", "step": 1}


def test_unmapped_fields_pass_through_untouched() -> None:
    profile = OpponentProfile(group_id="rival", field_aliases={"hint": "message"})
    assert profile.incoming({"their_extra": 1}) == {"their_extra": 1}


def test_a_profile_without_aliases_is_a_no_op() -> None:
    """The common case — a reference-compatible peer needs no translation."""
    profile = OpponentProfile(group_id="rival")
    payload = {"hint": "x", "step": 2}
    assert profile.outgoing(payload) is payload
    assert profile.incoming(payload) is payload


def test_adding_an_opponent_is_a_data_file_only(tmp_path: Path) -> None:
    """A6 pain #2: adapting to a team must never require a code change."""
    directory = tmp_path / "opponents"
    directory.mkdir()
    (directory / "rival.json").write_text(
        json.dumps(
            {
                "group_id": "rival-team",
                "tool_aliases": {"turn": "play_turn"},
                "field_aliases": {"hint": "message"},
                "response_timeout_sec": 60,
                "supports_session_token": True,
                "notes": "Sends hints as 'message'; slower on the first turn.",
            }
        ),
        encoding="utf-8",
    )
    registry = ProfileRegistry.load(directory)
    profile = registry.for_opponent("rival-team")
    assert profile.tool_for("turn", "receive_turn") == "play_turn"
    assert profile.outgoing({"hint": "x"}) == {"message": "x"}
    assert profile.response_timeout_sec == 60
    assert profile.supports_session_token


def test_unknown_keys_in_a_profile_are_ignored(tmp_path: Path) -> None:
    """A profile written in a hurry on match day must not crash the loader."""
    directory = tmp_path / "opponents"
    directory.mkdir()
    (directory / "x.json").write_text(
        json.dumps({"group_id": "x", "future_option": True}), encoding="utf-8"
    )
    assert ProfileRegistry.load(directory).for_opponent("x").group_id == "x"


def test_a_missing_profile_directory_is_not_an_error(tmp_path: Path) -> None:
    assert ProfileRegistry.load(tmp_path / "nothing").known == []


def test_the_tracker_starts_empty(tmp_path: Path) -> None:
    tracker = CountedGames.load(tmp_path / "counted.json")
    assert tracker.count == 0
    assert not tracker.passes_minimum
    assert tracker.remaining == MAX_COUNTED_MATCHES


def test_recording_a_match_increments_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "counted.json"
    CountedGames.load(path).record("rival-a", game_uid="uid-1", timestamp="2026-08-01")
    reloaded = CountedGames.load(path)
    assert reloaded.count == 1
    assert reloaded.history[0]["opponent"] == "rival-a"


def test_the_minimum_for_a_grade_is_two_different_teams(tmp_path: Path) -> None:
    """Book rule 31: fewer than two counted matches means no passing grade."""
    tracker = CountedGames.load(tmp_path / "counted.json")
    tracker.record("rival-a")
    assert not tracker.passes_minimum
    tracker.record("rival-b")
    assert tracker.passes_minimum


def test_the_same_opponent_cannot_be_counted_twice(tmp_path: Path) -> None:
    """Rule 52: one counted match per opponent; the rest are warm-ups."""
    tracker = CountedGames.load(tmp_path / "counted.json")
    tracker.record("rival-a")
    with pytest.raises(CountedGameError, match="already been counted"):
        tracker.record("rival-a")


def test_the_cap_of_ten_is_enforced(tmp_path: Path) -> None:
    tracker = CountedGames.load(tmp_path / "counted.json")
    for index in range(MAX_COUNTED_MATCHES):
        tracker.record(f"rival-{index}")
    assert tracker.remaining == 0
    with pytest.raises(CountedGameError, match="cap of 10"):
        tracker.record("one-too-many")


def test_check_can_count_warns_before_a_match_not_after(tmp_path: Path) -> None:
    """Better to discover it while scheduling than after playing six games."""
    tracker = CountedGames.load(tmp_path / "counted.json")
    tracker.record("rival-a")
    with pytest.raises(CountedGameError):
        tracker.check_can_count("rival-a")
    assert tracker.check_can_count("rival-b") is None


def test_the_declaration_comes_from_the_tracker(tmp_path: Path) -> None:
    """Rules 37-38: a false declaration disqualifies, so it is never hand-typed."""
    tracker = CountedGames.load(tmp_path / "counted.json")
    tracker.record("rival-a")
    tracker.record("rival-b")
    declaration = tracker.declaration()
    assert declaration["counted_matches_played"] == 2
    assert declaration["counted_matches_remaining"] == 8
    assert declaration["opponents_already_counted"] == ["rival-a", "rival-b"]


def test_the_audit_trail_records_every_change(tmp_path: Path) -> None:
    tracker = CountedGames.load(tmp_path / "counted.json")
    tracker.record("rival-a", game_uid="uid-a")
    tracker.record("rival-b", game_uid="uid-b")
    assert [entry["count_after"] for entry in tracker.history] == [1, 2]
    assert tracker.history[1]["game_uid"] == "uid-b"


def test_an_in_memory_tracker_does_not_require_a_path() -> None:
    tracker = CountedGames()
    tracker.record("rival-a")
    assert tracker.count == 1


def test_a_registry_built_in_memory_reports_what_it_knows() -> None:
    registry = ProfileRegistry({"rival": OpponentProfile(group_id="rival")})
    assert registry.known == ["rival"]
    assert registry.for_opponent("rival").group_id == "rival"


def test_outgoing_renames_are_applied_to_every_field() -> None:
    """Covers the outgoing alias path with more than one mapped field."""
    profile = OpponentProfile(
        group_id="rival", field_aliases={"hint": "message", "commit": "digest"}
    )
    assert profile.outgoing({"hint": "x", "commit": "c", "step": 1}) == {
        "message": "x",
        "digest": "c",
        "step": 1,
    }
