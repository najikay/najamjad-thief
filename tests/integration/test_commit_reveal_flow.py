"""End-to-end commit-reveal: two ledgers play a mini-game and audit each other.

This is the test that would have caught Assignment 6's class of failure — it
exercises the seams (ordering, secrecy, mutual verification) rather than each
unit in isolation.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.constants import EndReason
from najamjad_agent.domain.audit import audit_for_ending, audit_records, may_agree_result
from najamjad_agent.domain.crypto import step_payload
from najamjad_agent.domain.ledger import CommitLedger

STEPS = 6


def _play(cop: CommitLedger, thief: CommitLedger, tamper_step: int | None = None) -> None:
    """Run a scripted mini-game through the full four-step flow."""
    for step in range(1, STEPS + 1):
        cop_payload = step_payload(step, "police", 1, (0, step), "MOVE:E", "truth", "east", "s")
        thief_payload = step_payload(step, "thief", 1, (6, step), "MOVE:E", "lie", "north", "s")

        cop_commit = cop.commit(step, cop_payload)
        thief_commit = thief.commit(step, thief_payload)
        cop.record_opponent_commit(step, thief_commit)
        thief.record_opponent_commit(step, cop_commit)

        cop.acknowledge(step)
        thief.acknowledge(step)

        revealed_cop = cop.reveal(step)["payload"]
        revealed_thief = thief.reveal(step)["payload"]
        if tamper_step == step:
            revealed_thief = {**revealed_thief, "position": [0, 0]}
        thief.record_opponent_reveal(step, revealed_cop)
        cop.record_opponent_reveal(step, revealed_thief)


@pytest.fixture()
def peers() -> tuple[CommitLedger, CommitLedger]:
    return CommitLedger(sub_game=1), CommitLedger(sub_game=1)


def test_honest_game_ends_in_mutual_verified_ok(peers) -> None:
    cop, thief = peers
    _play(cop, thief)
    cop.open_audit()
    thief.open_audit()

    cop_view = audit_records(thief.opponent_records(cop.vault.reveal_all()))
    thief_view = audit_records(cop.opponent_records(thief.vault.reveal_all()))

    assert cop_view.banner == "Verified OK"
    assert thief_view.banner == "Verified OK"
    assert may_agree_result(cop_view, thief_view)


def test_a_cheating_peer_is_caught_and_forfeits(peers) -> None:
    """Rule 19: the tampered step is named and the game is technically void."""
    cop, thief = peers
    _play(cop, thief, tamper_step=4)
    cop.open_audit()
    thief.open_audit()

    verdict = audit_records(cop.opponent_records(thief.vault.reveal_all()))
    assert not verdict.passed
    assert verdict.failed_steps == [4]
    assert verdict.end_reason is EndReason.TAMPER_FORFEIT
    assert not may_agree_result(verdict, verdict)


def test_no_nonce_is_observable_before_the_audit_opens(peers) -> None:
    """Meta-test: scan everything transmitted mid-game for vault secrets."""
    cop, thief = peers
    transmitted: list[dict] = []
    for step in range(1, 4):
        payload = step_payload(step, "police", 1, (0, step), "MOVE:E", "truth", "east", "s")
        commit = cop.commit(step, payload)
        transmitted.append({"commit": commit})
        cop.acknowledge(step)
        transmitted.append(cop.reveal(step))

    wire = json.dumps(transmitted)
    cop.open_audit()
    secrets_in_play = cop.vault.reveal_all().values()
    assert secrets_in_play, "sanity: the vault holds nonces"
    assert all(nonce not in wire for nonce in secrets_in_play)
    assert "nonce" not in wire


def test_audit_is_skipped_when_the_opponent_vanishes(peers) -> None:
    cop, thief = peers
    _play(cop, thief)
    cop.open_audit()
    report = audit_for_ending(cop.audit_payload(), EndReason.TIMEOUT)
    assert report.skipped
    assert not may_agree_result(report, report)


def test_vault_survives_a_crash_mid_game(peers, tmp_path: Path) -> None:
    """A crash must not destroy the audit trail we are obliged to produce."""
    cop, thief = peers
    _play(cop, thief)
    spill = tmp_path / "vault.enc"
    cop.vault.spill(spill)

    cop.open_audit()
    expected = cop.vault.reveal_all()
    cop.vault.restore(spill)
    assert cop.vault.reveal_all() == expected
    assert audit_records(cop.audit_payload()).passed
