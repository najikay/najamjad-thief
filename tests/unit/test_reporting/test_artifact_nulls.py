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
        # The opponent's revealed records, carrying the step-0 declaration our
        # report reads their commit and token total off. Present here because
        # a fixture without one only ever exercises the "peer declared
        # nothing" path, which is what let `tokens: {theirs: 0}` ship as a
        # literal — every generated artifact agreed with the constant.
        "their_records": [
            {
                "payload": {
                    "step": 0,
                    "type": "system_spec",
                    "github_commit": "b0bacafe",
                    "tokens_total": (number - 1) * 400,
                },
                "nonce": "n0",
                "commit": "c0",
            }
        ],
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


@pytest.fixture(params=["this machine", "a runner with no clock and no gpu"])
def artifacts(request, tmp_path, monkeypatch) -> dict[str, dict]:
    """One filed two-game match, read back from disk.

    Run twice: once on whatever hardware this is, and once on a machine that
    cannot read its own clock and has no GPU. The second is not hypothetical —
    virtualised CI runners rarely expose `cpufreq`, and an AMD EPYC model string
    carries no clock either, so both fallbacks miss. That case took the whole
    declaration artifact down and nothing here noticed, because this laptop
    reports a clock and the tests only ever ran on it.
    """
    if request.param != "this machine":
        from najamjad_agent.shared import sysinfo

        monkeypatch.setattr(sysinfo, "CPU_MAX_FREQ", "/nonexistent/cpufreq")
        monkeypatch.setattr(sysinfo, "_cpu_name", lambda: "AMD EPYC 7763 64-Core Processor")
        monkeypatch.setattr(sysinfo, "_gpu_name", lambda: "none detected")
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
    """The A6 defect, as a gate over real output rather than a schema check.

    `cpu_freq_mhz` joins the allowed list only because a machine can genuinely
    fail to report it. Every other null here is a wiring bug.
    """
    allowed = (ALLOWED_NULL, "cpu_freq_mhz")
    for name, body in artifacts.items():
        offenders = [path for path in _nulls(body) if not path.endswith(allowed)]
        assert offenders == [], f"{name} carries nulls at {offenders}"


def test_the_hardware_declaration_carries_what_it_can(artifacts) -> None:
    """Rule 24 fairness: `cpu_freq_mhz` and `vram_gb` were null in every filing.

    `collect_spec()` never produced those keys, so `spec.get(...)` handed the
    declaration two `None`s. A blank on a fairness declaration reads as
    something withheld.

    The fields that are always knowable are asserted unconditionally. The clock
    is not one of them — and the first fix for that returned an `"unknown"`
    string, which `HardwareSpec` types as `int | None`, so it failed egress
    validation and destroyed the entire declaration rather than blanking one
    field. A gap is a gap; it must never be an outage.
    """
    declaration = next(body for name, body in artifacts.items() if name.startswith("declaration"))
    spec = declaration["groups"]["najamjad"]["hardware_spec"]

    for field in ("cpu_model", "cpu_cores", "ram_gb", "gpu_model", "vram_gb"):
        assert spec.get(field) is not None, f"{field} is null in the fairness declaration"
    assert "cpu_freq_mhz" in spec


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


def test_the_result_reports_the_opponents_own_commit_and_spend(artifacts) -> None:
    """Both fields used to be invented, and generated artifacts agreed with them.

    `github_commit[theirs]` fell back to a `their_commit` key nothing in this
    project ever wrote, and `tokens[theirs]` was a literal `0` — not a lookup
    that failed. Read here off the bytes on disk rather than from the row
    builder, because the defect was that nothing downstream ever disagreed.

    Their declared totals are 0 and 400, so mini-game 1 cost them 400. Game 2
    is the last and has no successor to subtract from: reported as 0, because
    understating one game beats inventing a figure they never claimed.
    """
    result = next(body for name, body in artifacts.items() if name.startswith("result"))
    first, second = result["sub_games"]

    assert first["github_commit"]["rival"] == "b0bacafe"
    assert first["github_commit"]["najamjad"] != "unknown"
    assert first["tokens"]["rival"] == 400
    assert second["tokens"]["rival"] == 0
    assert result["final_result"]["tokens_total_series"]["rival"] == 400


def test_each_group_declaration_is_sealed_against_later_edits(artifacts) -> None:
    """Rule 24's `signature`, filled at last — read off the generated bytes.

    The field has been in the schema, defaulted to `""`, since the artifact was
    written, and nothing produced one: we filed hardware specs with no proof
    they had not been edited afterwards.

    Verified the way a reader would: pop the key, re-hash the rest, compare.
    That only works if we signed the block *without* its own signature, which
    is the property this pins.
    """
    from najamjad_agent.reporting.consensus import settlement_signature

    declaration = next(body for name, body in artifacts.items() if name.startswith("declaration"))

    for group, block in declaration["groups"].items():
        assert block["signature"], f"{group} declaration is unsigned"
        body = {key: value for key, value in block.items() if key != "signature"}
        assert settlement_signature(body) == block["signature"], group
