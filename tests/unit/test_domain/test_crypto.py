"""Tests for commit-reveal sealing, including byte-compatibility with the goldens."""

import json
from pathlib import Path

import pytest

from najamjad_agent.domain.crypto import (
    NONCE_BYTES,
    CommitMismatchError,
    commit_of,
    new_nonce,
    require_match,
    seal,
    step_payload,
    verify,
)
from najamjad_agent.protocol.canonical import canonical_json

GOLDEN_LOG = (
    Path(__file__).resolve().parents[3]
    / "tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json"
)


@pytest.fixture()
def payload() -> dict:
    return step_payload(
        step=3,
        role="police",
        sub_game=1,
        position=(2, 4),
        move="MOVE:E",
        intent="lie",
        hint="I am circling the northern blocks",
        state="grid=7x7;self=[2, 4];barriers=[]",
    )


def test_golden_log_records_all_verify() -> None:
    """Byte-compatibility with the lecturer's implementation (ADR-012).

    If this breaks, every opponent's audit of our log fails and the match is a
    technical loss for us — so it is checked against real reference data.
    """
    records = json.loads(GOLDEN_LOG.read_text(encoding="utf-8"))["records"]
    assert len(records) == 19
    assert all(verify(r["payload"], r["nonce"], r["commit"]) for r in records)


def test_canonical_json_is_sorted_compact_and_unicode_preserving() -> None:
    encoded = canonical_json({"b": 1, "a": "שלום"})
    assert encoded == '{"a":"שלום","b":1}'


def test_seal_produces_a_verifiable_commit(payload: dict) -> None:
    record = seal(payload)
    assert verify(record.payload, record.nonce, record.commit)


def test_nonce_is_sixteen_random_bytes() -> None:
    nonce = new_nonce()
    assert len(nonce) == NONCE_BYTES * 2
    assert int(nonce, 16) >= 0


def test_each_seal_draws_a_fresh_nonce(payload: dict) -> None:
    nonces = {seal(payload).nonce for _ in range(50)}
    assert len(nonces) == 50, "nonce reuse would leak repeated moves"


def test_same_payload_with_different_nonces_gives_different_commits(payload: dict) -> None:
    assert seal(payload).commit != seal(payload).commit


def test_commit_is_deterministic_for_a_fixed_nonce(payload: dict) -> None:
    assert commit_of(payload, "abc123") == commit_of(payload, "abc123")


def test_key_order_does_not_change_the_commit(payload: dict) -> None:
    reordered = dict(reversed(list(payload.items())))
    assert commit_of(reordered, "n") == commit_of(payload, "n")


@pytest.mark.parametrize("field", ["step", "position", "move", "intent", "hint", "state"])
def test_tampering_with_any_field_breaks_verification(payload: dict, field: str) -> None:
    record = seal(payload)
    tampered = {**record.payload, field: "TAMPERED"}
    assert not verify(tampered, record.nonce, record.commit)


def test_wrong_nonce_fails_verification(payload: dict) -> None:
    record = seal(payload)
    assert not verify(record.payload, new_nonce(), record.commit)


def test_require_match_raises_on_mismatch(payload: dict) -> None:
    record = seal(payload)
    with pytest.raises(CommitMismatchError, match="commit mismatch"):
        require_match({**record.payload, "move": "MOVE:W"}, record.nonce, record.commit)


def test_require_match_is_silent_on_a_good_record(payload: dict) -> None:
    record = seal(payload)
    assert require_match(record.payload, record.nonce, record.commit) is None


def test_public_view_exposes_only_the_commitment(payload: dict) -> None:
    """Pre-audit secrecy: neither the nonce NOR the payload reaches a peer.

    The payload holds our position, move and intent. Sending it would hand the
    opponent perfect information and leave nothing to reveal at audit.
    """
    view = seal(payload).public_view()
    assert set(view) == {"commit"}
    assert "nonce" not in view
    assert "position" not in str(view)


def test_audit_view_reveals_the_nonce(payload: dict) -> None:
    record = seal(payload)
    assert record.audit_view()["nonce"] == record.nonce


def test_step_payload_has_the_interop_field_shape(payload: dict) -> None:
    assert set(payload) == {
        "step",
        "role",
        "sub_game",
        "position",
        "move",
        "intent",
        "hint",
        "state",
    }
    assert payload["position"] == [2, 4], "positions serialize as JSON lists"


def test_step_payload_accepts_extra_fields(payload: dict) -> None:
    extended = step_payload(
        step=1,
        role="thief",
        sub_game=2,
        position=(0, 0),
        move="STAY",
        intent="truth",
        hint="",
        state="s",
        extra={"tokens_step": 12, "capture_claim": False},
    )
    assert extended["tokens_step"] == 12
    assert extended["capture_claim"] is False


def test_unicode_and_nested_payloads_round_trip() -> None:
    payload = {"hint": "מסתתר ליד הגשר 🌉", "nested": {"b": [1, 2, {"c": None}]}}
    record = seal(payload)
    assert verify(record.payload, record.nonce, record.commit)
