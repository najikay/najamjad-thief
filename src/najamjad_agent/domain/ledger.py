"""The per-mini-game commit ledger enforcing the four-step reveal order.

Commit → Acknowledge → Reveal (nonce withheld) → Audit (nonces revealed).

The ordering is not advisory: revealing a move before the opponent has locked
their commitment would let them adapt, and revealing a nonce early breaks the
whole scheme. The ledger therefore refuses out-of-order operations rather than
trusting the turn loop to call it correctly, and it owns the nonce vault so a
nonce cannot escape through a side door.
"""

from dataclasses import dataclass, field
from typing import Any

from .crypto import SealedRecord, seal
from .nonce_vault import NonceVault


class ProtocolOrderError(Exception):
    """Raised when a commit-reveal step happens out of order."""


@dataclass
class StepEntry:
    """One of our steps as it moves through the four-step flow."""

    record: SealedRecord
    acknowledged: bool = False
    revealed: bool = False


@dataclass
class CommitLedger:
    """Our sealed steps plus the opponent's commitments, per mini-game."""

    sub_game: int = 1
    vault: NonceVault = field(default_factory=NonceVault)
    _ours: dict[int, StepEntry] = field(default_factory=dict)
    _theirs: dict[int, str] = field(default_factory=dict)
    _their_reveals: dict[int, dict[str, Any]] = field(default_factory=dict)

    def commit(self, step: int, payload: dict[str, Any]) -> str:
        """Seal a step and return only the public commitment hash."""
        if step in self._ours:
            raise ProtocolOrderError(f"step {step} already committed")
        record = seal(payload)
        self._ours[step] = StepEntry(record=record)
        self.vault.store(step, record.nonce)
        return record.commit

    def acknowledge(self, step: int) -> None:
        """Record that the opponent locked onto our commitment."""
        self._require_committed(step)
        self._ours[step].acknowledged = True

    def reveal(self, step: int) -> dict[str, Any]:
        """Reveal the move and hint — never the nonce (that waits for audit)."""
        self._require_committed(step)
        entry = self._ours[step]
        if not entry.acknowledged:
            raise ProtocolOrderError(f"step {step} not acknowledged; reveal would leak our move")
        entry.revealed = True
        return entry.record.public_view()

    def record_opponent_commit(self, step: int, commit: str) -> None:
        """Store the opponent's commitment for later verification."""
        if step in self._theirs:
            raise ProtocolOrderError(f"opponent already committed step {step}")
        self._theirs[step] = commit

    def record_opponent_reveal(self, step: int, payload: dict[str, Any]) -> None:
        """Store the opponent's revealed payload; requires a prior commitment."""
        if step not in self._theirs:
            raise ProtocolOrderError(f"opponent revealed step {step} without committing")
        self._their_reveals[step] = payload

    def open_audit(self) -> None:
        """End of mini-game: unlock nonce reveal for the audit exchange."""
        self.vault.open_audit()

    def audit_payload(self) -> list[dict[str, Any]]:
        """Our full records with nonces, for the opponent to re-verify."""
        self.vault.require_open()
        return [self._ours[step].record.audit_view() for step in sorted(self._ours)]

    def opponent_records(self, nonces: dict[int, str]) -> list[dict[str, Any]]:
        """Assemble the opponent's audit records from their revealed nonces."""
        assembled = []
        for step in sorted(self._their_reveals):
            assembled.append(
                {
                    "payload": self._their_reveals[step],
                    "nonce": nonces.get(step, ""),
                    "commit": self._theirs.get(step, ""),
                }
            )
        return assembled

    def _require_committed(self, step: int) -> None:
        if step not in self._ours:
            raise ProtocolOrderError(f"step {step} was never committed")
