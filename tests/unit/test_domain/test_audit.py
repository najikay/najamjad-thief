"""Tests for the mutual audit: verdicts, tamper localisation, hostile payloads."""

import json
from pathlib import Path

import pytest

from najamjad_agent.constants import EndReason
from najamjad_agent.domain.audit import (
    AuditReport,
    audit_for_ending,
    audit_records,
    may_agree_result,
)
from najamjad_agent.domain.crypto import seal, step_payload

GOLDEN_LOG = (
    Path(__file__).resolve().parents[3]
    / "tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json"
)


def _records(count: int = 5) -> list[dict]:
    return [
        seal(
            step_payload(
                step=step,
                role="thief",
                sub_game=1,
                position=(step, 0),
                move="MOVE:S",
                intent="truth",
                hint=f"step {step}",
                state=f"grid=7x7;self=[{step}, 0]",
            )
        ).audit_view()
        for step in range(1, count + 1)
    ]


def test_honest_log_passes_with_verified_ok() -> None:
    report = audit_records(_records())
    assert report.passed
    assert report.banner == "Verified OK"
    assert report.verified_steps == [1, 2, 3, 4, 5]
    assert report.end_reason is None


def test_golden_reference_log_passes_audit() -> None:
    records = json.loads(GOLDEN_LOG.read_text(encoding="utf-8"))["records"]
    assert audit_records(records).passed


@pytest.mark.parametrize("target", [1, 3, 5])
def test_single_tampered_record_is_localised(target: int) -> None:
    """Rule 19: one mismatch voids the game — and we name the exact step."""
    records = _records()
    records[target - 1]["payload"] = {**records[target - 1]["payload"], "move": "MOVE:N"}
    report = audit_records(records)
    assert not report.passed
    assert report.failed_steps == [target]
    assert report.banner == "TAMPERED"
    assert report.end_reason is EndReason.TAMPER_FORFEIT


def test_swapped_nonce_is_detected() -> None:
    records = _records()
    records[0]["nonce"], records[1]["nonce"] = records[1]["nonce"], records[0]["nonce"]
    assert audit_records(records).failed_steps == [1, 2]


def test_audit_is_symmetric_for_both_peers() -> None:
    """Both sides must reach the same verdict from the same evidence."""
    records = _records()
    records[2]["commit"] = "0" * 64
    ours = audit_records(records)
    theirs = audit_records(json.loads(json.dumps(records)))
    assert (ours.passed, ours.failed_steps) == (theirs.passed, theirs.failed_steps)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-a-list",
        [],
        [{"payload": {"step": 1}}],
        [{"payload": {"step": 1}, "nonce": "n"}],
        [{"payload": "flat", "nonce": "n", "commit": "c"}],
        [{"payload": {"step": 1}, "nonce": 5, "commit": "c"}],
        ["totally wrong"],
    ],
)
def test_malformed_audit_payloads_return_a_verdict_not_a_crash(payload) -> None:
    """A hostile peer must not be able to crash us into a technical loss."""
    report = audit_records(payload)
    assert isinstance(report, AuditReport)
    assert not report.passed
    assert report.errors


def test_audit_is_skipped_when_the_protocol_never_closed() -> None:
    for reason in (EndReason.TIMEOUT, EndReason.STOPPED, EndReason.OPPONENT_QUIT):
        report = audit_for_ending(_records(), reason)
        assert report.skipped
        assert report.banner == "AUDIT SKIPPED"


def test_audit_runs_for_clean_endings() -> None:
    for reason in (EndReason.CAPTURE, EndReason.SURVIVAL):
        assert audit_for_ending(_records(), reason).passed


def test_result_agreement_requires_both_audits_to_pass() -> None:
    """Book rule 36: no agreed result without a clean mutual audit."""
    good = audit_records(_records())
    bad = audit_records([{"payload": {"step": 1}, "nonce": "n", "commit": "c"}])
    assert may_agree_result(good, good)
    assert not may_agree_result(good, bad)
    assert not may_agree_result(bad, good)
