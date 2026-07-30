"""End-of-game mutual audit — cryptography decides, not human judgement.

Both peers exchange their full logs including nonces and re-hash every step. A
single mismatch voids the game for the forger (book rule 19, "iron law"), and a
passing audit is the precondition for agreeing the shared result (rule 36).

Malformed audit payloads are answered with a verdict, never an exception: a peer
that sends garbage must not be able to crash us into a technical loss.
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import EndReason
from .crypto import verify

# Endings where the protocol never reached a clean close, so there is nothing
# to audit; matches the reference implementation's SKIPPED_AUDIT behaviour.
SKIP_AUDIT_REASONS = (EndReason.TIMEOUT, EndReason.STOPPED, EndReason.OPPONENT_QUIT)
REQUIRED_FIELDS = ("payload", "nonce", "commit")


@dataclass(frozen=True)
class AuditReport:
    """Outcome of auditing one peer's revealed records."""

    passed: bool
    verified_steps: list[int] = field(default_factory=list)
    failed_steps: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    #: How the opponent says the mini-game ended, from their audit envelope.
    #: We have always *sent* ours and never read theirs, so the one channel the
    #: protocol gives the two agents for agreeing on an outcome was used in one
    #: direction only.
    #: The opponent's revealed records, exactly as they sent them.
    #:
    #: We received these every mini-game, verified every commit hash in them,
    #: and then dropped them on the floor — `AuditReport` kept only pass/fail.
    #: So the one independently-verified copy of the opponent's moves that we
    #: are ever given passed through our hands and was discarded, and a replay
    #: could only ever show our own half of the game.
    their_records: list[dict[str, Any]] = field(default_factory=list)
    their_claim: str = ""
    #: Set when their claim contradicts ours. Rules 33-35 void both teams on
    #: contradictory reports, so this is worth knowing while both agents are
    #: still talking rather than after the lecturer compares two emails.
    disputed: bool = False

    @property
    def banner(self) -> str:
        """Replay-viewer banner text (book rule 20)."""
        if self.skipped:
            return "AUDIT SKIPPED"
        return "Verified OK" if self.passed else "TAMPERED"

    @property
    def end_reason(self) -> EndReason | None:
        """Forfeit reason when tampering was proven."""
        return None if self.passed or self.skipped else EndReason.TAMPER_FORFEIT


def _step_of(record: Any, index: int) -> int:
    """Best-effort step number for reporting, falling back to position."""
    if isinstance(record, dict) and isinstance(record.get("payload"), dict):
        step = record["payload"].get("step")
        if isinstance(step, int):
            return step
    return index


def audit_records(records: Any) -> AuditReport:
    """Re-verify every revealed record from the opponent."""
    if not isinstance(records, list):
        return AuditReport(passed=False, errors=["records must be a list"])
    if not records:
        return AuditReport(passed=False, errors=["no records supplied"])
    verified: list[int] = []
    failed: list[int] = []
    errors: list[str] = []
    for index, record in enumerate(records):
        step = _step_of(record, index)
        problem = _validate(record)
        if problem:
            failed.append(step)
            errors.append(f"step {step}: {problem}")
        elif verify(record["payload"], record["nonce"], record["commit"]):
            verified.append(step)
        else:
            failed.append(step)
            errors.append(f"step {step}: commit does not match revealed payload")
    return AuditReport(passed=not failed, verified_steps=verified, failed_steps=failed, errors=errors)


def _validate(record: Any) -> str | None:
    """Structural check of one record; returns a reason when unusable."""
    if not isinstance(record, dict):
        return "record is not an object"
    missing = [name for name in REQUIRED_FIELDS if name not in record]
    if missing:
        return f"missing {', '.join(missing)}"
    if not isinstance(record["payload"], dict):
        return "payload is not an object"
    if not isinstance(record["nonce"], str) or not isinstance(record["commit"], str):
        return "nonce and commit must be strings"
    return None


def audit_for_ending(records: Any, end_reason: EndReason) -> AuditReport:
    """Audit unless the ending means the protocol never closed cleanly."""
    if end_reason in SKIP_AUDIT_REASONS:
        return AuditReport(passed=False, skipped=True)
    return audit_records(records)


def may_agree_result(ours: AuditReport, theirs: AuditReport) -> bool:
    """True only when both audits passed — the gate on result agreement."""
    return ours.passed and theirs.passed
