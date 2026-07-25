"""Tests for wire schemas: tolerant ingress, strict validation, interop shapes."""

import pytest

from najamjad_agent.protocol.ingress import parse_message
from najamjad_agent.protocol.schemas_wire import (
    AuditPayload,
    ControlMessage,
    NegotiateMessage,
    NegotiateTerms,
    TurnMessage,
)

TURN = {"step": 3, "sender": "rival", "commit": "a" * 64, "hint": "near the docks"}


def test_turn_message_parses_the_reference_field_set() -> None:
    message = TurnMessage.model_validate(
        {
            **TURN,
            "smell_grid": {"3,3": 0.9},
            "timestamp": "2026-07-25T10:00:00+00:00",
            "barrier_placed": [3, 4],
            "capture_claim": True,
            "claim_response": False,
            "win_claim": "capture",
        }
    )
    assert message.step == 3
    assert message.smell_grid == {"3,3": 0.9}
    assert message.barrier_placed == [3, 4]
    assert message.capture_claim is True


def test_unknown_fields_are_kept_not_rejected() -> None:
    """A6 pain #2: an opponent's extra key must never forfeit a match."""
    result = parse_message(TurnMessage, {**TURN, "their_custom_flag": 7, "telemetry": {"x": 1}})
    assert result.ok
    assert result.unknown_fields == ["telemetry", "their_custom_flag"]
    assert result.model.extras["their_custom_flag"] == 7


def test_missing_commit_is_rejected() -> None:
    """The commit is the cryptographic anchor; a turn without one is unusable."""
    result = parse_message(TurnMessage, {"step": 1, "sender": "rival"})
    assert not result.ok
    assert any("commit" in error for error in result.errors)


def test_empty_commit_is_rejected() -> None:
    assert not parse_message(TurnMessage, {**TURN, "commit": ""}).ok


def test_negative_step_is_rejected() -> None:
    assert not parse_message(TurnMessage, {**TURN, "step": -1}).ok


def test_wrong_types_are_reported_not_raised() -> None:
    result = parse_message(TurnMessage, {**TURN, "smell_grid": "not-a-map"})
    assert not result.ok
    assert result.errors


def test_malformed_barrier_cell_is_rejected() -> None:
    result = parse_message(TurnMessage, {**TURN, "barrier_placed": [1, 2, 3]})
    assert not result.ok
    assert any("row, col" in error for error in result.errors)


def test_non_object_payloads_are_handled() -> None:
    for raw in ["a string", 42, None, ["list"]]:
        result = parse_message(TurnMessage, raw)
        assert not result.ok
        assert "expected an object" in result.errors[0]


def test_error_response_is_structured_for_the_peer() -> None:
    result = parse_message(TurnMessage, {"step": 1})
    response = result.error_response("receive_turn")
    assert response["accepted"] is False
    assert response["kind"] == "receive_turn"
    assert response["errors"]


def test_negotiate_message_requires_signature_and_nonce() -> None:
    assert parse_message(NegotiateMessage, {"identity": "us", "terms": {}, "nonce": "n", "signature": "s"}).ok
    assert not parse_message(NegotiateMessage, {"identity": "us", "terms": {}}).ok


def test_negotiate_terms_enforce_appendix_f_minimums() -> None:
    """A peer may raise a minimum, never lower it (book rule 12)."""
    good = NegotiateTerms.model_validate(
        {"grid_size": 10, "max_barriers": 20, "max_moves": 40, "survival_threshold": 40}
    )
    assert good.grid_size == 10
    for field, bad in [
        ("grid_size", 6),
        ("max_barriers", 13),
        ("max_moves", 34),
        ("survival_threshold", 34),
    ]:
        terms = {"grid_size": 7, "max_barriers": 14, "max_moves": 35, "survival_threshold": 35}
        terms[field] = bad
        assert not parse_message(NegotiateTerms, terms).ok, f"{field}={bad} must be refused"


def test_negotiate_terms_default_to_six_mini_games() -> None:
    """Appendix F Table 18, not the reference simulator's num_games=1."""
    terms = NegotiateTerms.model_validate(
        {"grid_size": 7, "max_barriers": 14, "max_moves": 35, "survival_threshold": 35}
    )
    assert terms.num_games == 6


def test_audit_payload_requires_complete_records() -> None:
    good = {"sender": "rival", "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}]}
    assert parse_message(AuditPayload, good).ok
    bad = {"sender": "rival", "records": [{"payload": {"step": 1}, "commit": "c"}]}
    assert not parse_message(AuditPayload, bad).ok


def test_audit_payload_rejects_empty_nonce() -> None:
    raw = {"records": [{"payload": {}, "nonce": "", "commit": "c"}]}
    assert not parse_message(AuditPayload, raw).ok


@pytest.mark.parametrize("kind", ["enable", "status", "restart", "quit"])
def test_control_message_accepts_known_kinds(kind: str) -> None:
    assert parse_message(ControlMessage, {"kind": kind}).ok


def test_control_message_rejects_unknown_kinds() -> None:
    """Guessing at an unimplemented verb is how peers desynchronise."""
    result = parse_message(ControlMessage, {"kind": "self_destruct"})
    assert not result.ok
    assert any("unknown control kind" in error for error in result.errors)
