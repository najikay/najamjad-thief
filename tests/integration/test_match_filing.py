"""A finished match must produce the four artifacts and the emailed result.

The gap this closes was not a bug in any component — every piece below was
built and unit-tested. It was simply never *called*: a full six-game match
against the reference produced **zero artifacts on our side** while the opponent
wrote all four, because `ArtifactWriter` had no caller outside the test suite.

The most valuable test here is the last one. It compares our emitted
`result_*.json` field by field against the lecturer's own sample, because a
report the grader parses differently from everyone else's is exactly how
Assignment 6 lost marks — and no amount of internal consistency catches it.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.domain.scoring import SeriesResult
from najamjad_agent.reporting.filing import MatchFiler, final_result_block, sub_game_rows

GOLDEN = Path("tests/goldens/artifacts/result_segal-police-team-vs-segal-thief-team.json")
GROUPS = ("najamjad", "rival")
GAME_ID = "najamjad-vs-rival"


class Outcome:
    """The scored half of one mini-game."""

    def __init__(self, ours: int, theirs: int) -> None:
        self.our_score, self.their_score = ours, theirs


def games(count: int = 2) -> list[dict]:
    """Finished mini-games as `MatchRunner` records them."""
    return [
        {
            "sub_game": number,
            "role": "police" if number % 2 else "thief",
            "end_reason": "capture" if number % 2 else "survival",
            "steps": 11,
            "audit": "Verified OK",
            "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c" * 64}],
        }
        for number in range(1, count + 1)
    ]


def series() -> SeriesResult:
    return SeriesResult(
        total_score={"najamjad": 30, "rival": 10},
        sub_games_won={"najamjad": 2, "rival": 0},
        ties=0,
        winner_group="najamjad",
        series_tie=False,
    )


def group_block(group_id: str) -> dict:
    """The static per-group block the declaration requires of both teams."""
    return {
        "group_id": group_id,
        "group_name": group_id.title(),
        "members": ["A", "B"],
        "repos": {"cop": f"https://example.invalid/{group_id}-cop"},
        "mcp_servers": {"cop": f"https://{group_id}.invalid/mcp"},
        "llm_model": "claude-haiku-4-5-20251001",
    }


def declaration() -> dict:
    """The `groups` mapping itself — the writer wraps it, so wrapping it here
    too produced `groups.groups` and the egress gate rightly refused it."""
    return {name: group_block(name) for name in GROUPS}


@pytest.fixture
def filed(tmp_path):
    """One filed match, on disk."""
    filer = MatchFiler(tmp_path, GAME_ID, "uid-1234", GROUPS)
    written = filer.file_match(
        games(), [Outcome(20, 5), Outcome(10, 5)], series(),
        terms={"board_and_agents": {}, "movement_and_barriers": {}, "scoring": {},
               "pheromones": {}},
        config_sha256="a" * 64,
        groups_block=declaration(),
    )
    return tmp_path, written


def test_all_four_artifact_kinds_are_written(filed):
    """The deliverable is four files, not one."""
    _, written = filed

    assert Path(written["declaration"]).exists()
    assert Path(written["result"]).exists()
    assert len(written["config"]) == 2 and len(written["log"]) == 2


def test_every_artifact_carries_the_same_game_uid(filed):
    """Files from two matches must be impossible to mix up."""
    workspace, _ = filed
    uids = {json.loads(path.read_text(encoding="utf-8"))["game_uid"]
            for path in workspace.glob("*.json")}

    assert uids == {"uid-1234"}


def test_the_result_names_both_peers_copies_of_each_log(filed):
    """`log_files` lets a reader find the two logs whose commits must agree."""
    _, written = filed
    rows = json.loads(Path(written["result"]).read_text(encoding="utf-8"))["sub_games"]

    assert set(rows[0]["log_files"]) == set(GROUPS)
    assert rows[0]["log_files"]["najamjad"].endswith("_g01.json")


def test_roles_are_recorded_for_both_sides_and_are_opposite():
    """A role we held implies the one they held; recording only ours is half a
    row, and the grader reads both."""
    rows = sub_game_rows(games(1), [Outcome(20, 5)], GROUPS, GAME_ID)

    assert rows[0]["roles"] == {"najamjad": "police", "rival": "thief"}


def test_a_drawn_mini_game_has_no_winner_rather_than_a_default_one():
    rows = sub_game_rows(games(1), [Outcome(2, 2)], GROUPS, GAME_ID)

    assert rows[0]["winner_group"] is None
    assert rows[0]["tie"] is True


def test_the_audit_verdict_travels_with_the_row():
    rows = sub_game_rows(games(1), [Outcome(20, 5)], GROUPS, GAME_ID)

    assert rows[0]["audit"] == {"log_verified": True, "tampered": False}


def test_final_result_matches_the_league_table_shape():
    block = final_result_block(series(), tokens={"najamjad": 4577, "rival": 0})

    assert block["winner_group"] == "najamjad"
    assert block["tokens_total_series"]["najamjad"] == 4577
    assert block["series_tie"] is False


def test_nothing_is_sent_when_no_mail_sender_is_wired(tmp_path):
    """Offline runs must file the artifacts and say the mail did not go —
    silence would read as a sent report."""
    events: list[dict] = []
    filer = MatchFiler(tmp_path, GAME_ID, "uid", GROUPS, emit=events.append)

    assert filer.send(tmp_path / "anything.json") is None
    assert any(event["event"] == "report.not_sent" for event in events)


def test_the_result_is_sent_through_the_configured_sender(tmp_path):
    sent: list[Path] = []

    class Sender:
        def send_report(self, path, subject):
            sent.append(path)
            return "msg-1"

    filer = MatchFiler(tmp_path, GAME_ID, "uid", GROUPS, sender=Sender())

    assert filer.send(tmp_path / "result.json") == "msg-1"
    assert sent


# --------------------------------------------------------------- the parity test


def test_our_result_carries_every_field_the_lecturers_sample_does(filed):
    """The check that would have caught Assignment 6's format loss.

    Internal consistency proves nothing here: our report is read by a grader
    against everyone else's. Compared against the lecturer's own artifact, not
    against our idea of it.
    """
    _, written = filed
    ours = json.loads(Path(written["result"]).read_text(encoding="utf-8"))
    theirs = json.loads(GOLDEN.read_text(encoding="utf-8"))

    expected = {key for key in theirs if not key.startswith("_")}
    assert expected - set(ours) == set(), f"missing from our result: {expected - set(ours)}"

    expected_row = {key for key in theirs["sub_games"][0] if not key.startswith("_")}
    missing = expected_row - set(ours["sub_games"][0])
    assert missing == set(), f"missing from our sub_game rows: {missing}"

    expected_final = {key for key in theirs["final_result"] if not key.startswith("_")}
    assert expected_final - set(ours["final_result"]) == set()
