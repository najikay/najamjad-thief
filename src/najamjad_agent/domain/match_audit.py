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


def send_reveal(ledger: CommitLedger, transport: Any, sender: str = "") -> dict[str, Any]:
    """Open our ledger and hand the peer everything they need to check us.

    Enveloped as `{"sender": …, "records": […]}`, which is what the wire schema
    declares and what `receive_reveal` reads back. We used to send the bare
    list: the peer's validator rejected it, the reveal never arrived, and both
    sides recorded TAMPERED for a game neither had cheated in.

    Every in-memory test passed throughout, because the fake transport wrapped
    the list on the way past and the real one did not.
    """
    ledger.open_audit()
    payload = {"sender": sender, "records": ledger.audit_payload()}
    transport.send_audit(payload)
    return payload


def receive_reveal(transport: Any, timeout: float) -> AuditReport:
    """Re-hash whatever the peer revealed; silence is a failed audit, not a crash."""
    reply = transport.receive_audit(timeout)
    if reply is None:
        return AuditReport(passed=False, errors=["opponent revealed nothing before the deadline"])
    records = reply.get("records") if isinstance(reply, dict) else reply
    return audit_records(records)


def exchange_audit(
    ledger: CommitLedger, transport: Any, timeout: float = 30.0, sender: str = ""
) -> AuditReport:
    """Reveal ours, verify theirs, and report on theirs.

    Ours goes first unconditionally. Withholding our nonces until we have seen
    theirs would be indistinguishable, from their side, from preparing to
    forge — and rule 18 only protects a nonce until the audit, not through it.
    """
    send_reveal(ledger, transport, sender)
    return receive_reveal(transport, timeout)
