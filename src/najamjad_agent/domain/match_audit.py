"""The end-of-game reveal exchange (book rules 18-20).

Both peers hand over their sealed records, nonces included, and each re-hashes
the other's. This is the moment the whole commit-reveal scheme pays for itself:
until now neither side could check anything, and after it neither side can
rewrite anything.

A peer who sends nothing, or garbage, gets a verdict rather than an exception.
Silence at audit time is a common shape of cheating — and crashing on it would
turn their failure into our technical loss.
"""

from typing import Any

from .audit import AuditReport, audit_records
from .ledger import CommitLedger


def send_reveal(ledger: CommitLedger, transport: Any) -> list[dict[str, Any]]:
    """Open our ledger and hand the peer everything they need to check us."""
    ledger.open_audit()
    payload = ledger.audit_payload()
    transport.send_audit(payload)
    return payload


def receive_reveal(transport: Any, timeout: float) -> AuditReport:
    """Re-hash whatever the peer revealed; silence is a failed audit, not a crash."""
    reply = transport.receive_audit(timeout)
    if reply is None:
        return AuditReport(passed=False, errors=["opponent revealed nothing before the deadline"])
    records = reply.get("records") if isinstance(reply, dict) else reply
    return audit_records(records)


def exchange_audit(ledger: CommitLedger, transport: Any, timeout: float = 30.0) -> AuditReport:
    """Reveal ours, verify theirs, and report on theirs.

    Ours goes first unconditionally. Withholding our nonces until we have seen
    theirs would be indistinguishable, from their side, from preparing to
    forge — and rule 18 only protects a nonce until the audit, not through it.
    """
    send_reveal(ledger, transport)
    return receive_reveal(transport, timeout)
