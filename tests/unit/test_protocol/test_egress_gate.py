"""Tests for the egress gate — the structural fix for A6's `agreement: null`."""

import pytest

from najamjad_agent.protocol.egress import (
    EgressBlockedError,
    egress_is_valid,
    validate_egress,
)
from najamjad_agent.protocol.schemas_report import ResultArtifact

SHA = "b" * 64


def _result(**overrides) -> dict:
    payload = {
        "game_id": "najamjad-vs-rival",
        "game_uid": "uid-123",
        "groups": ["najamjad", "rival"],
        "num_sub_games": 6,
        "sub_games": [
            {
                "sub_game_number": 1,
                "roles": {"najamjad": "police", "rival": "thief"},
                "result": "capture",
                "winner_group": "najamjad",
                "tie": False,
                "score": {"najamjad": 20, "rival": 5},
                "audit": {"log_verified": True, "tampered": False},
            }
        ],
        "final_result": {
            "total_score": {"najamjad": 20, "rival": 5},
            "sub_games_won": {"najamjad": 1, "rival": 0},
            "ties": 0,
            "winner_group": "najamjad",
            "series_tie": False,
        },
        "mutual_agreement": {"sha256": SHA, "confirmed": True},
    }
    payload.update(overrides)
    return payload


def test_a_complete_report_passes_the_gate() -> None:
    parsed = validate_egress(ResultArtifact, _result(), kind="result")
    assert parsed.mutual_agreement.confirmed is True
    assert parsed.final_result.winner_group == "najamjad"


def test_null_agreement_is_refused() -> None:
    """The exact Assignment 6 defect: `confirmed: null` must never ship."""
    payload = _result(mutual_agreement={"sha256": SHA, "confirmed": None})
    with pytest.raises(EgressBlockedError) as caught:
        validate_egress(ResultArtifact, payload, kind="result")
    assert any("mutual_agreement.confirmed" in problem for problem in caught.value.problems)


def test_missing_agreement_block_is_refused() -> None:
    payload = _result()
    del payload["mutual_agreement"]
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result")


def test_missing_confirmed_key_is_refused() -> None:
    payload = _result(mutual_agreement={"sha256": SHA})
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result")


@pytest.mark.parametrize("value", ["true", "yes", 1, 0, "", []])
def test_truthy_lookalikes_are_refused(value) -> None:
    """A string "true" would serialise into JSON the grader reads as text."""
    payload = _result(mutual_agreement={"sha256": SHA, "confirmed": value})
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result")


def test_confirmed_false_is_allowed_because_it_is_honest() -> None:
    """A truthful `false` is valid data; only null/absent is corrupt."""
    payload = _result(mutual_agreement={"sha256": SHA, "confirmed": False})
    assert validate_egress(ResultArtifact, payload, kind="result").mutual_agreement.confirmed is False


def test_short_agreement_hash_is_refused() -> None:
    payload = _result(mutual_agreement={"sha256": "abc", "confirmed": True})
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result")


def test_blocked_send_raises_an_operator_alert() -> None:
    """Silence is what made A6 unfixable; a blocked send must be loud."""
    alerts: list[dict] = []
    payload = _result(mutual_agreement={"sha256": SHA, "confirmed": None})
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result", alert=alerts.append)
    assert alerts[0]["event"] == "egress.blocked"
    assert alerts[0]["kind"] == "result"
    assert alerts[0]["problems"]


def test_unexpected_field_in_our_own_report_is_refused() -> None:
    """A stray key means our builder is wrong — fail locally, not at the grader."""
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, _result(typo_field="oops"), kind="result")


def test_missing_required_identity_is_refused() -> None:
    payload = _result()
    del payload["game_uid"]
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, payload, kind="result")


def test_report_with_no_sub_games_is_refused() -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, _result(sub_games=[]), kind="result")


def test_wrong_group_count_is_refused() -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress(ResultArtifact, _result(groups=["only-us"]), kind="result")


def test_probe_reports_validity_without_raising() -> None:
    assert egress_is_valid(ResultArtifact, _result())
    assert not egress_is_valid(
        ResultArtifact, _result(mutual_agreement={"sha256": SHA, "confirmed": None})
    )


def test_error_message_names_the_artifact_and_reasons() -> None:
    payload = _result(mutual_agreement={"sha256": SHA, "confirmed": None})
    with pytest.raises(EgressBlockedError, match="result blocked before sending"):
        validate_egress(ResultArtifact, payload, kind="result")
