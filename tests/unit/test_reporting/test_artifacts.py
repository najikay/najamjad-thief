"""Tests for the four lifecycle artifacts — validated before they are written."""

import json
from pathlib import Path

import pytest

from najamjad_agent.protocol.egress import EgressBlockedError
from najamjad_agent.reporting.artifacts import ArtifactWriter

GAME_ID = "najamjad-vs-rival"
GAME_UID = "uid-abc"
GROUPS = ("najamjad", "rival")
SHA = "c" * 64

SUB_GAMES = [
    {
        "sub_game_number": 1,
        "roles": {"najamjad": "police", "rival": "thief"},
        "result": "capture",
        "winner_group": "najamjad",
        "tie": False,
        "score": {"najamjad": 20, "rival": 5},
        "audit": {"log_verified": True, "tampered": False},
    }
]
FINAL = {
    "total_score": {"najamjad": 20, "rival": 5},
    "sub_games_won": {"najamjad": 1, "rival": 0},
    "ties": 0,
    "winner_group": "najamjad",
    "series_tie": False,
}
GROUPS_BLOCK = {
    "group_1": {
        "group_id": "najamjad",
        "group_name": "NajAmjad",
        "members": ["Naji Kayal", "Amjad Abed"],
        "repos": {"cop": "https://github.com/najikay/najamjad-cop", "thief": "https://github.com/najikay/najamjad-thief"},
    },
    "group_2": {
        "group_id": "rival",
        "group_name": "Rival",
        "members": ["Someone"],
        "repos": {"cop": "https://example.com/cop", "thief": "https://example.com/thief"},
    },
}
TERMS = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {"max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
    "scoring": {"capture_cop": 20, "capture_thief": 5},
    "pheromones": {"pheromone_center_intensity": 0.9},
}
SUMMARY = {
    "sub_game_number": 1,
    "group_id": "najamjad",
    "role": "police",
    "opponent_group_id": "rival",
    "result": "capture",
    "steps": 12,
    "audit": {"passed": True, "verified_steps": 12, "failed_steps": []},
}
RECORDS = [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}]


@pytest.fixture()
def writer(tmp_path: Path) -> ArtifactWriter:
    return ArtifactWriter(tmp_path / "matches" / "rival", GAME_ID, GAME_UID, GROUPS)


def test_the_declaration_is_written_with_the_book_filename(writer: ArtifactWriter) -> None:
    path = writer.write_declaration(GROUPS_BLOCK)
    assert path.name == f"declaration_{GAME_ID}.json"
    assert json.loads(path.read_text())["game_uid"] == GAME_UID


def test_the_config_carries_its_locked_hash(writer: ArtifactWriter) -> None:
    path = writer.write_config(1, TERMS, SHA)
    payload = json.loads(path.read_text())
    assert path.name == f"config_{GAME_ID}_g01.json"
    assert payload["config_sha256"] == SHA
    assert payload["agreed_between"] == ["najamjad", "rival"]


def test_the_log_carries_the_sealed_chain_and_agreement(writer: ArtifactWriter) -> None:
    path = writer.write_log(1, SUMMARY, RECORDS, "rival", True, SUB_GAMES)
    payload = json.loads(path.read_text())
    assert path.name == f"log_{GAME_ID}_g01.json"
    assert payload["records"] == RECORDS
    assert payload["mutual_agreement"]["confirmed"] is True


def test_the_result_is_written_for_emailing(writer: ArtifactWriter) -> None:
    path = writer.write_result(SUB_GAMES, FINAL, "rival", True)
    payload = json.loads(path.read_text())
    assert path.name == f"result_{GAME_ID}.json"
    assert payload["final_result"]["winner_group"] == "najamjad"
    assert len(payload["mutual_agreement"]["sha256"]) == 64


def test_all_four_artifacts_share_one_game_uid(writer: ArtifactWriter) -> None:
    """A mismatched uid is how files from different matches get conflated."""
    paths = [
        writer.write_declaration(GROUPS_BLOCK),
        writer.write_config(1, TERMS, SHA),
        writer.write_log(1, SUMMARY, RECORDS, "rival", True, SUB_GAMES),
        writer.write_result(SUB_GAMES, FINAL, "rival", True),
    ]
    uids = {json.loads(path.read_text())["game_uid"] for path in paths}
    assert uids == {GAME_UID}


def test_artifacts_land_in_the_match_workspace(writer: ArtifactWriter, tmp_path: Path) -> None:
    """A match must be reconstructable from its folder alone."""
    writer.write_result(SUB_GAMES, FINAL, "rival", True)
    assert (tmp_path / "matches" / "rival" / f"result_{GAME_ID}.json").exists()


def test_an_unagreed_result_still_records_a_real_boolean(writer: ArtifactWriter) -> None:
    payload = json.loads(writer.write_result(SUB_GAMES, FINAL, "rival", False).read_text())
    assert payload["mutual_agreement"]["confirmed"] is False


def test_a_null_agreement_can_never_be_written(writer: ArtifactWriter) -> None:
    """The A6 defect, refused at the source rather than coerced to False.

    Coercing None to False would be worse than crashing: it writes a
    plausible-looking report that misstates what happened.
    """
    with pytest.raises(TypeError, match="must be a bool from reconciliation"):
        writer.write_result(SUB_GAMES, FINAL, "rival", None)  # type: ignore[arg-type]


def test_a_truthy_non_boolean_agreement_is_also_refused(writer: ArtifactWriter) -> None:
    for value in ("true", 1, "yes"):
        with pytest.raises(TypeError):
            writer.write_result(SUB_GAMES, FINAL, "rival", value)  # type: ignore[arg-type]


def test_an_invalid_artifact_is_never_written_to_disk(tmp_path: Path) -> None:
    """Validation happens before the file exists, not after."""
    writer = ArtifactWriter(tmp_path / "match", GAME_ID, GAME_UID, GROUPS)
    with pytest.raises(EgressBlockedError):
        writer.write_result([], FINAL, "rival", True)
    assert not (tmp_path / "match" / f"result_{GAME_ID}.json").exists()


def test_a_blocked_write_raises_an_operator_alert(tmp_path: Path) -> None:
    alerts: list[dict] = []
    writer = ArtifactWriter(tmp_path / "m", GAME_ID, GAME_UID, GROUPS, alert=alerts.append)
    with pytest.raises(EgressBlockedError):
        writer.write_result([], FINAL, "rival", True)
    assert alerts and alerts[0]["event"] == "egress.blocked"


def test_both_peers_write_the_same_agreement_signature(tmp_path: Path) -> None:
    """Rule 35: contradictory reports void the match for both teams."""
    ours = ArtifactWriter(tmp_path / "a", GAME_ID, GAME_UID, ("najamjad", "rival"))
    theirs = ArtifactWriter(tmp_path / "b", GAME_ID, GAME_UID, ("rival", "najamjad"))
    our_payload = json.loads(ours.write_result(SUB_GAMES, FINAL, "rival", True).read_text())
    their_payload = json.loads(theirs.write_result(SUB_GAMES, FINAL, "najamjad", True).read_text())
    assert our_payload["mutual_agreement"]["sha256"] == their_payload["mutual_agreement"]["sha256"]


def test_artifacts_are_written_in_canonical_form(writer: ArtifactWriter) -> None:
    """Byte-stable output so two peers' files can be compared directly."""
    first = writer.write_result(SUB_GAMES, FINAL, "rival", True).read_text()
    second = writer.write_result(SUB_GAMES, FINAL, "rival", True).read_text()
    assert first == second
    assert " " not in first.split('"game_id"')[0]


def test_the_links_block_names_all_four_files(writer: ArtifactWriter) -> None:
    payload = json.loads(writer.write_declaration(GROUPS_BLOCK).read_text())
    assert set(payload["links"]) == {"declaration", "config", "log", "result"}


def test_extra_fields_reach_the_declaration(writer: ArtifactWriter) -> None:
    path = writer.write_declaration(GROUPS_BLOCK, max_tokens_per_game=200_000, num_sub_games=6)
    payload = json.loads(path.read_text())
    assert payload["max_tokens_per_game"] == 200_000
    assert payload["num_sub_games"] == 6
