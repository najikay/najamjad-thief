"""Generate the real artifact set and assert nothing is null or hollow.

Assignment 6 emailed a report containing `agreement: null`, and a later series
emailed one claiming three games were drawn when nobody drew them. Both were
found by a human reading the file, not by a test — every schema check passed,
because a `null` in an optional field and a wrong-but-well-typed value are both
valid JSON.

So this generates all four artifact kinds through the production `MatchFiler`
and reads the bytes back. `winner_group` is the one legitimate null: a drawn or
technical mini-game has no winner, and inventing one would be worse.
"""

import json

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.series import SeriesResult, SubGameOutcome
from najamjad_agent.negotiation.identity import spec_for_declaration
from najamjad_agent.reporting.filing import MatchFiler
from najamjad_agent.reporting.result_blocks import declaration_group
from najamjad_agent.sdk.match_filing import _config_body
from tests.role_config import load_role_config

GROUPS = ("najamjad", "rival")
#: The only field allowed to be null, and only where there genuinely is no winner.
ALLOWED_NULL = "winner_group"


def _identity(group_id: str) -> dict:
    return {
        "group_id": group_id,
        "group_name": group_id.title(),
        "members": ["Naji Kayal", "Amjad Abed"],
        "repos": {"cop": "https://example.invalid/cop", "thief": "https://example.invalid/thief"},
        "mcp_servers": {"cop": "https://example.invalid", "thief": "https://example.invalid"},
        "llm_model": "cli-default",
        "spec": spec_for_declaration(),
        "counted_matches_played": 0,
    }


def _game(number: int, reason: str) -> dict:
    return {
        "sub_game": number,
        "role": "police" if number % 2 else "thief",
        "end_reason": reason,
        "audit": "Verified OK",
        "started_at": f"2026-08-06T20:0{number}:00Z",
        "ended_at": f"2026-08-06T20:1{number}:00Z",
        "steps": 12,
        "score": {"najamjad": 20, "rival": 5},
        "tokens": 140,
        "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}],
        "verified_steps": [1, 2],
        "failed_steps": [],
        "their_claim": reason,
        "disputed": False,
    }


def _outcome(number: int, reason: EndReason) -> SubGameOutcome:
    return SubGameOutcome(
        sub_game=number,
        role=Role.COP if number % 2 else Role.THIEF,
        end_reason=reason,
        our_score=20,
        their_score=5,
        steps=12,
    )


@pytest.fixture()
def artifacts(tmp_path) -> dict[str, dict]:
    """One filed two-game match, read back from disk."""
    manager = load_role_config()
    filer = MatchFiler(tmp_path, "najamjad-vs-rival", "uid-1", GROUPS)
    filer.file_match(
        [_game(1, "capture"), _game(2, "survival")],
        [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.SURVIVAL)],
        SeriesResult(
            total_score={"najamjad": 40, "rival": 10},
            sub_games_won={"najamjad": 2, "rival": 0},
            ties=0,
            winner_group="najamjad",
            series_tie=False,
        ),
        _config_body(manager),
        "a" * 64,
        {group: declaration_group(_identity(group)) for group in GROUPS},
        emission={"scent": "full", "hint": "spoken"},
    )
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(tmp_path.glob("*.json"))
    }


def _nulls(value, path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in _nulls(item, f"{path}.{key}")]
    if isinstance(value, list):
        return [found for i, item in enumerate(value) for found in _nulls(item, f"{path}[{i}]")]
    return [path] if value is None else []


def test_every_artifact_kind_is_written(artifacts) -> None:
    """Rule 35 scores a missing file as not having played."""
    kinds = {name.split("_")[0] for name in artifacts}

    assert kinds == {"declaration", "config", "log", "result"}


def test_no_artifact_carries_an_unexplained_null(artifacts) -> None:
    """The A6 defect, as a gate over real output rather than a schema check."""
    for name, body in artifacts.items():
        offenders = [path for path in _nulls(body) if not path.endswith(ALLOWED_NULL)]
        assert offenders == [], f"{name} carries nulls at {offenders}"


def test_the_hardware_declaration_is_complete(artifacts) -> None:
    """Rule 24 fairness: `cpu_freq_mhz` and `vram_gb` were null in every filing.

    `collect_spec()` never produced those keys, so `spec.get(...)` handed the
    declaration two `None`s. A blank on a fairness declaration reads as
    something withheld.
    """
    declaration = next(body for name, body in artifacts.items() if name.startswith("declaration"))
    spec = declaration["groups"]["najamjad"]["hardware_spec"]

    for field in ("cpu_model", "cpu_cores", "cpu_freq_mhz", "ram_gb", "gpu_model", "vram_gb"):
        assert spec.get(field) is not None, f"{field} is null in the fairness declaration"


def test_the_declaration_agrees_with_the_result_about_the_match(artifacts) -> None:
    """Our own artifact set used to contradict itself in front of a grader.

    `num_sub_games` came from a schema default of 6 while the result computed it
    from the games actually played, so a two-game match filed both 6 and 2.
    """
    declaration = next(body for name, body in artifacts.items() if name.startswith("declaration"))
    result = next(body for name, body in artifacts.items() if name.startswith("result"))

    assert declaration["num_sub_games"] == result["num_sub_games"] == 2
    assert declaration["game_started_at"] and declaration["game_ended_at"]


def test_the_audit_summary_reports_audited_steps_not_game_length(artifacts) -> None:
    """`verified_steps` was the step count, so it agreed with nothing."""
    log = next(body for name, body in artifacts.items() if name.startswith("log"))
    audit = log["summary"]["audit"]

    assert audit["verified_steps"] == 2, "this is the audit's count, not the game's length"
    assert audit["failed_steps"] == []
