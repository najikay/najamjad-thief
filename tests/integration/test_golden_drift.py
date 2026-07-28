"""Artifacts from a real run must keep the shape the lecturer's samples have (T-2113).

The goldens prove our *crypto* still matches the reference. This proves our
*artifacts* still do — a different failure, and a quieter one. A field that
disappears from a report does not break a test, does not fail an audit, and is
invisible until a grader opens the file next to somebody else's.

It has already happened twice: `result_*.json` shipped without
`schema_version`, `report_type` or `timezone` because the writer serialised the
raw payload instead of the validated model, and sub-game rows shipped without
`log_files`. Both were valid JSON, self-consistent, and wrong.

The comparison is **against the lecturer's own artifacts**, never against a
snapshot of our own output — a snapshot of ourselves would have agreed with both
defects.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.domain.scoring import SeriesResult
from najamjad_agent.reporting.filing import MatchFiler

GOLDENS = Path("tests/goldens/artifacts")
RESULT_GOLDEN = GOLDENS / "result_segal-police-team-vs-segal-thief-team.json"
LOG_GOLDEN = GOLDENS / "log_segal-police-team-vs-segal-thief-team_g01.json"
GROUPS = ("najamjad", "rival")
GAME_ID = "najamjad-vs-rival"


class Outcome:
    def __init__(self, ours: int, theirs: int) -> None:
        self.our_score, self.their_score = ours, theirs


def group_block(group_id: str) -> dict:
    return {
        "group_id": group_id,
        "group_name": group_id.title(),
        "members": ["A", "B"],
        "repos": {"cop": f"https://example.invalid/{group_id}"},
        "mcp_servers": {"cop": f"https://{group_id}.invalid/mcp"},
        "llm_model": "claude-haiku-4-5-20251001",
    }


@pytest.fixture(scope="module")
def produced(tmp_path_factory) -> dict[str, dict]:
    """One filed match, parsed back off disk."""
    workspace = tmp_path_factory.mktemp("drift")
    filer = MatchFiler(workspace, GAME_ID, "uid-drift", GROUPS)
    written = filer.file_match(
        games=[{"sub_game": 1, "role": "police", "end_reason": "capture", "steps": 11,
                "audit": "Verified OK",
                "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c" * 64}]}],
        outcomes=[Outcome(20, 5)],
        result=SeriesResult(total_score={"najamjad": 20, "rival": 5},
                            sub_games_won={"najamjad": 1, "rival": 0}, ties=0,
                            winner_group="najamjad", series_tie=False),
        terms={"board_and_agents": {}, "movement_and_barriers": {}, "scoring": {},
               "pheromones": {}},
        config_sha256="a" * 64,
        groups_block={name: group_block(name) for name in GROUPS},
    )
    return {
        kind: json.loads(Path(paths[0] if isinstance(paths, list) else paths).read_text("utf-8"))
        for kind, paths in written.items()
    }


def public_keys(payload: dict) -> set[str]:
    """Keys excluding the samples' `_`-prefixed documentation notes."""
    return {key for key in payload if not key.startswith("_")}


def test_the_result_keeps_every_top_level_field_the_sample_has(produced):
    """The exact drift that shipped a report without its schema version."""
    expected = public_keys(json.loads(RESULT_GOLDEN.read_text(encoding="utf-8")))

    missing = expected - set(produced["result"])

    assert not missing, f"our result has drifted; missing {sorted(missing)}"


def test_the_sub_game_rows_keep_every_field_the_sample_has(produced):
    """Where `log_files` went missing."""
    sample = json.loads(RESULT_GOLDEN.read_text(encoding="utf-8"))["sub_games"][0]

    missing = public_keys(sample) - set(produced["result"]["sub_games"][0])

    assert not missing, f"sub-game rows have drifted; missing {sorted(missing)}"


def test_the_final_result_block_keeps_its_shape(produced):
    """The block the league table is built from."""
    sample = json.loads(RESULT_GOLDEN.read_text(encoding="utf-8"))["final_result"]

    missing = public_keys(sample) - set(produced["result"]["final_result"])

    assert not missing, f"final_result has drifted; missing {sorted(missing)}"


def test_the_log_artifact_keeps_the_shape_a_replay_needs(produced):
    """A log missing a field is a log the opponent cannot verify us from."""
    if not LOG_GOLDEN.exists():
        pytest.skip("no log golden checked in")
    expected = public_keys(json.loads(LOG_GOLDEN.read_text(encoding="utf-8")))

    missing = expected - set(produced["log"])

    assert not missing, f"log artifact has drifted; missing {sorted(missing)}"


def test_the_declaration_names_both_groups(produced):
    """Each side's block; the opponent's declaration indexes ours directly."""
    assert set(produced["declaration"]["groups"]) == set(GROUPS)


def test_every_artifact_carries_the_identity_that_links_them(produced):
    """Files from two matches must be impossible to mix up."""
    for kind, payload in produced.items():
        assert payload.get("game_uid") == "uid-drift", f"{kind} lost its game_uid"
        assert payload.get("game_id") == GAME_ID, f"{kind} lost its game_id"


def test_the_versions_we_declare_match_the_samples(produced):
    """A grader parses by schema version; drifting it silently is worse than
    drifting a field, because the whole file is then read against the wrong
    expectations."""
    sample = json.loads(RESULT_GOLDEN.read_text(encoding="utf-8"))

    assert produced["result"]["schema_version"] == sample["schema_version"]
    assert produced["result"]["report_type"] == sample["report_type"]
