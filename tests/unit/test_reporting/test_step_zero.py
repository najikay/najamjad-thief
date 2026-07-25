"""Tests for the Step-0 signed declaration and hardware/commit capture."""

import json
from pathlib import Path

import pytest

from najamjad_agent.domain.crypto import verify
from najamjad_agent.reporting.step_zero import (
    build_declaration,
    declaration_is_complete,
    seal_declaration,
)
from najamjad_agent.shared.sysinfo import collect_spec, git_commit
from najamjad_agent.shared.version import CODE_VERSION

GOLDEN_LOG = (
    Path(__file__).resolve().parents[2]
    / "goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json"
)


@pytest.fixture()
def declaration() -> dict:
    return build_declaration(
        group_name="NajAmjad",
        role="police",
        sub_game=1,
        model="claude-fable-5",
        opponent_group="rival-team",
        spec={"os": "Linux 6.6", "cpu_type": "Intel i7", "cpu_cores": 8, "ram_gb": 16.0},
        commit="a" * 40,
    )


def test_declaration_carries_every_mandatory_field(declaration: dict) -> None:
    """Book rule 53 + Ch. 5: hardware, model, code version, commit, identity."""
    assert declaration["step"] == 0
    assert declaration["type"] == "system_spec"
    assert declaration["github_commit"] == "a" * 40
    assert declaration["code_version"] == CODE_VERSION
    assert declaration["group_name"] == "NajAmjad"
    assert declaration["role"] == "police"
    assert declaration["sub_game"] == 1
    assert declaration["model"] == "claude-fable-5"
    assert declaration["spec"]["cpu_cores"] == 8


def test_declaration_matches_the_golden_record_shape(declaration: dict) -> None:
    """Interop: our Step-0 must be comparable with the reference log's record."""
    golden = json.loads(GOLDEN_LOG.read_text(encoding="utf-8"))["records"][0]["payload"]
    assert golden["step"] == declaration["step"]
    assert golden["type"] == declaration["type"]
    for field in ("spec", "model", "code_version", "group_name", "role"):
        assert field in declaration, f"golden field {field} missing from ours"
    for field in ("os", "cpu_type", "cpu_cores", "ram_gb"):
        assert field in golden["spec"] and field in declaration["spec"]


def test_declaration_is_sealed_and_verifiable(declaration: dict) -> None:
    record = seal_declaration(declaration)
    assert verify(record.payload, record.nonce, record.commit)


def test_sealed_declaration_cannot_be_revised_afterwards(declaration: dict) -> None:
    """Claiming weaker hardware after losing must fail the audit."""
    record = seal_declaration(declaration)
    revised = {**record.payload, "spec": {**record.payload["spec"], "cpu_cores": 2}}
    assert not verify(revised, record.nonce, record.commit)


def test_token_totals_start_at_zero_and_are_carried(declaration: dict) -> None:
    assert declaration["tokens_total"] == 0
    assert build_declaration("g", "thief", 1, "m", tokens_total=1234)["tokens_total"] == 1234


def test_completeness_check_passes_for_a_full_declaration(declaration: dict) -> None:
    assert declaration_is_complete(declaration) == []


def test_completeness_check_flags_an_unresolved_commit(declaration: dict) -> None:
    problems = declaration_is_complete({**declaration, "github_commit": "unknown"})
    assert any("rule 53" in problem for problem in problems)


def test_completeness_check_flags_missing_hardware(declaration: dict) -> None:
    problems = declaration_is_complete({**declaration, "spec": {"os": "Linux"}})
    assert any("cpu_type" in problem for problem in problems)
    assert any("computational-fairness" in problem for problem in problems)


def test_completeness_check_flags_empty_identity(declaration: dict) -> None:
    assert any("group_name" in p for p in declaration_is_complete({**declaration, "group_name": ""}))


def test_collect_spec_returns_usable_values_on_this_machine() -> None:
    spec = collect_spec()
    assert set(spec) >= {"os", "cpu_type", "cpu_cores", "ram_gb", "gpu_type", "python"}
    assert spec["cpu_cores"] != "unknown"


def test_git_commit_resolves_in_this_repository() -> None:
    commit = git_commit(str(Path(__file__).resolve().parents[3]))
    assert commit == "unknown" or len(commit) == 40


def test_git_commit_degrades_gracefully_outside_a_repository(tmp_path: Path) -> None:
    assert git_commit(str(tmp_path)) == "unknown"
