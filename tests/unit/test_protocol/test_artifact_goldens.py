"""Golden tests: our schemas must accept the lecturer's own sample artifacts.

If these fail, our reports are shaped differently from what the grader and every
opponent expect — the quiet way to lose points with working code.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.protocol.schemas_artifacts import (
    ConfigArtifact,
    DeclarationArtifact,
    LogArtifact,
)
from najamjad_agent.protocol.schemas_report import (
    ResultArtifact,
    artifact_links,
    config_filename,
    declaration_filename,
    log_filename,
    result_filename,
)

GOLDENS = Path(__file__).resolve().parents[2] / "goldens/artifacts"
GAME_ID = "segal-police-team-vs-segal-thief-team"

pytestmark = pytest.mark.goldens


def _load(name: str) -> dict:
    return json.loads((GOLDENS / name).read_text(encoding="utf-8"))


def test_reference_declaration_validates() -> None:
    artifact = DeclarationArtifact.model_validate(_load(declaration_filename(GAME_ID)))
    assert artifact.game_id == GAME_ID
    assert set(artifact.groups) == {"group_1", "group_2"}
    assert artifact.groups["group_1"].repos["cop"].startswith("http")


def test_reference_declaration_carries_four_repo_links() -> None:
    """Book rule 49: cop+thief repos for both teams."""
    artifact = DeclarationArtifact.model_validate(_load(declaration_filename(GAME_ID)))
    links = [group.repos[role] for group in artifact.groups.values() for role in ("cop", "thief")]
    assert len(links) == 4


def test_reference_declaration_hardware_spec_parses() -> None:
    artifact = DeclarationArtifact.model_validate(_load(declaration_filename(GAME_ID)))
    spec = artifact.groups["group_1"].hardware_spec
    assert spec is not None
    assert spec.cpu_cores >= 1
    assert spec.ram_gb > 0


def test_reference_config_validates_and_keeps_its_hash() -> None:
    artifact = ConfigArtifact.model_validate(_load(config_filename(GAME_ID, 1)))
    assert len(artifact.config_sha256) == 64
    assert artifact.board_and_agents["grid_size"] == 7
    assert artifact.scoring["capture_cop"] == 20


def test_reference_log_validates_with_its_records() -> None:
    artifact = LogArtifact.model_validate(_load(log_filename(GAME_ID, 1)))
    assert len(artifact.records) == 19
    assert artifact.summary.audit.passed is True
    assert artifact.mutual_agreement.confirmed is True


def test_reference_result_validates() -> None:
    artifact = ResultArtifact.model_validate(_load(result_filename(GAME_ID)))
    assert artifact.final_result.winner_group == "segal-police-team"
    assert artifact.mutual_agreement.confirmed is True
    assert artifact.sub_games[0].score["segal-police-team"] == 20


def test_all_four_artifacts_share_one_game_uid() -> None:
    """A mismatched uid is how files from different matches get conflated."""
    uids = {
        _load(name)["game_uid"]
        for name in (
            declaration_filename(GAME_ID),
            config_filename(GAME_ID, 1),
            log_filename(GAME_ID, 1),
            result_filename(GAME_ID),
        )
    }
    assert len(uids) == 1


def test_filename_helpers_reproduce_the_reference_names() -> None:
    assert declaration_filename(GAME_ID) == f"declaration_{GAME_ID}.json"
    assert config_filename(GAME_ID, 1) == f"config_{GAME_ID}_g01.json"
    assert log_filename(GAME_ID, 12) == f"log_{GAME_ID}_g12.json"
    assert result_filename(GAME_ID) == f"result_{GAME_ID}.json"


def test_generated_filenames_exist_as_golden_files() -> None:
    for name in (
        declaration_filename(GAME_ID),
        config_filename(GAME_ID, 1),
        log_filename(GAME_ID, 1),
        result_filename(GAME_ID),
    ):
        assert (GOLDENS / name).exists(), f"{name} does not match the reference naming"


def test_links_block_matches_the_reference_roles() -> None:
    links = artifact_links(GAME_ID, 1)
    assert set(links) == {"declaration", "config", "log", "result"}
    assert links["config"].endswith("_g01.json")


def test_non_dict_input_is_passed_through_for_pydantic_to_reject() -> None:
    """The documentation-key stripper must not mask a wrong-typed payload."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResultArtifact.model_validate("not an object")


def test_our_result_round_trips_through_the_schema() -> None:
    """Serialising our parsed model must not lose or rename anything."""
    original = _load(result_filename(GAME_ID))
    reparsed = ResultArtifact.model_validate(original).model_dump(mode="json")
    assert reparsed["game_uid"] == original["game_uid"]
    assert reparsed["final_result"]["total_score"] == original["final_result"]["total_score"]
    assert reparsed["mutual_agreement"]["confirmed"] is True
