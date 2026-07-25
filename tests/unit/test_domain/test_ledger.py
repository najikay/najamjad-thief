"""Tests for the four-step commit-reveal flow enforced by the ledger."""

import pytest

from najamjad_agent.domain.audit import audit_records
from najamjad_agent.domain.crypto import commit_of, step_payload
from najamjad_agent.domain.ledger import CommitLedger, ProtocolOrderError
from najamjad_agent.domain.nonce_vault import NonceSealedError


def _payload(step: int) -> dict:
    return step_payload(
        step=step,
        role="police",
        sub_game=1,
        position=(0, step),
        move="MOVE:E",
        intent="truth",
        hint=f"moving east, step {step}",
        state=f"grid=7x7;self=[0, {step}]",
    )


@pytest.fixture()
def ledger() -> CommitLedger:
    return CommitLedger(sub_game=1)


def test_commit_returns_only_a_hash(ledger: CommitLedger) -> None:
    commit = ledger.commit(1, _payload(1))
    assert isinstance(commit, str)
    assert len(commit) == 64


def test_committing_a_step_twice_is_refused(ledger: CommitLedger) -> None:
    ledger.commit(1, _payload(1))
    with pytest.raises(ProtocolOrderError, match="already committed"):
        ledger.commit(1, _payload(1))


def test_reveal_before_acknowledge_is_refused(ledger: CommitLedger) -> None:
    """Revealing early would let an unlocked opponent adapt to our move."""
    ledger.commit(1, _payload(1))
    with pytest.raises(ProtocolOrderError, match="not acknowledged"):
        ledger.reveal(1)


def test_reveal_marks_the_step_without_exposing_the_payload(ledger: CommitLedger) -> None:
    """Our move stays sealed until the audit; reveal only unlocks the flow."""
    ledger.commit(1, _payload(1))
    ledger.acknowledge(1)
    revealed = ledger.reveal(1)
    assert set(revealed) == {"commit"}
    assert "nonce" not in revealed


def test_acknowledging_an_uncommitted_step_is_refused(ledger: CommitLedger) -> None:
    with pytest.raises(ProtocolOrderError, match="never committed"):
        ledger.acknowledge(7)


def test_nonces_stay_sealed_until_audit_opens(ledger: CommitLedger) -> None:
    ledger.commit(1, _payload(1))
    with pytest.raises(NonceSealedError):
        ledger.audit_payload()
    ledger.open_audit()
    assert len(ledger.audit_payload()) == 1


def test_audit_payload_is_ordered_and_verifiable(ledger: CommitLedger) -> None:
    for step in (3, 1, 2):
        ledger.commit(step, _payload(step))
    ledger.open_audit()
    records = ledger.audit_payload()
    assert [record["payload"]["step"] for record in records] == [1, 2, 3]
    assert audit_records(records).passed


def test_opponent_reveal_without_commit_is_refused(ledger: CommitLedger) -> None:
    """A peer must not be able to invent a move after seeing ours."""
    with pytest.raises(ProtocolOrderError, match="without committing"):
        ledger.record_opponent_reveal(1, _payload(1))


def test_duplicate_opponent_commit_is_refused(ledger: CommitLedger) -> None:
    ledger.record_opponent_commit(1, "a" * 64)
    with pytest.raises(ProtocolOrderError, match="already committed"):
        ledger.record_opponent_commit(1, "b" * 64)


def test_opponent_records_assemble_for_audit(ledger: CommitLedger) -> None:
    payload = _payload(1)
    nonce = "f" * 32
    ledger.record_opponent_commit(1, commit_of(payload, nonce))
    ledger.record_opponent_reveal(1, payload)
    records = ledger.opponent_records({1: nonce})
    assert audit_records(records).passed


def test_opponent_lying_at_reveal_is_caught_by_audit(ledger: CommitLedger) -> None:
    """The whole point: a peer cannot change its move after committing."""
    honest = _payload(1)
    nonce = "e" * 32
    ledger.record_opponent_commit(1, commit_of(honest, nonce))
    ledger.record_opponent_reveal(1, {**honest, "position": [6, 6]})
    assert not audit_records(ledger.opponent_records({1: nonce})).passed


def test_missing_opponent_nonce_fails_audit_rather_than_crashing(ledger: CommitLedger) -> None:
    payload = _payload(1)
    ledger.record_opponent_commit(1, commit_of(payload, "a" * 32))
    ledger.record_opponent_reveal(1, payload)
    report = audit_records(ledger.opponent_records({}))
    assert not report.passed
