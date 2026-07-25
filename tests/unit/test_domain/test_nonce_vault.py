"""Tests for nonce custody: secrecy before audit, integrity after."""

from pathlib import Path

import pytest

from najamjad_agent.domain.crypto import new_nonce
from najamjad_agent.domain.nonce_vault import NonceSealedError, NonceVault


@pytest.fixture()
def vault() -> NonceVault:
    filled = NonceVault()
    for step in range(1, 4):
        filled.store(step, new_nonce())
    return filled


def test_vault_starts_sealed(vault: NonceVault) -> None:
    assert vault.audit_open is False


def test_reveal_is_refused_before_audit(vault: NonceVault) -> None:
    """Book rule 18: an early nonce leak lets the opponent invert our commits."""
    with pytest.raises(NonceSealedError, match="secret until"):
        vault.reveal(1)
    with pytest.raises(NonceSealedError):
        vault.reveal_all()


def test_reveal_works_once_audit_opens(vault: NonceVault) -> None:
    vault.open_audit()
    assert isinstance(vault.reveal(1), str)
    assert len(vault.reveal_all()) == 3


def test_step_count_is_available_while_sealed(vault: NonceVault) -> None:
    """Counting steps leaks nothing, so the UI may show progress."""
    assert vault.step_count == 3


def test_storing_a_step_twice_is_refused(vault: NonceVault) -> None:
    with pytest.raises(ValueError, match="already has a stored nonce"):
        vault.store(1, new_nonce())


def test_spill_file_does_not_contain_plaintext_nonces(vault: NonceVault, tmp_path: Path) -> None:
    path = tmp_path / "vault.enc"
    vault.spill(path)
    blob = path.read_text(encoding="utf-8")
    vault.open_audit()
    assert all(nonce not in blob for nonce in vault.reveal_all().values())


def test_restore_recovers_custody_after_a_crash(vault: NonceVault, tmp_path: Path) -> None:
    path = tmp_path / "vault.enc"
    vault.spill(path)
    vault.open_audit()
    expected = vault.reveal_all()
    vault.restore(path)
    assert vault.reveal_all() == expected


def test_a_different_vault_cannot_decrypt_the_spill(vault: NonceVault, tmp_path: Path) -> None:
    """The key never leaves memory, so a stolen spill file is useless."""
    path = tmp_path / "vault.enc"
    vault.spill(path)
    vault.open_audit()
    real_nonces = set(vault.reveal_all().values())

    intruder = NonceVault()
    try:
        intruder.restore(path)
    except (UnicodeDecodeError, ValueError):
        return  # Garbage plaintext failed to parse — the expected outcome.
    intruder.open_audit()
    assert not (set(intruder.reveal_all().values()) & real_nonces), "decrypted with a foreign key"
