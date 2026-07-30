"""The end-of-game reveal exchange (book rules 18-20).

Both peers hand over their sealed records, nonces included, and each re-hashes
the other's. This is the moment the whole commit-reveal scheme pays for itself:
until now neither side could check anything, and after it neither side can
rewrite anything.

A peer who sends nothing, or garbage, gets a verdict rather than an exception.
Silence at audit time is a common shape of cheating — and crashing on it would
turn their failure into our technical loss.
"""

from dataclasses import replace
from typing import Any

from .audit import AuditReport, audit_records
from .ledger import CommitLedger


def send_reveal(
    ledger: CommitLedger, transport: Any, sender: str = "", result_claim: str = ""
) -> dict[str, Any]:
    """Open our ledger and hand the peer everything they need to check us.

    Enveloped as `{"sender": …, "records": […], "result_claim": …}` — exactly
    the three fields the reference's `AuditPayload` declares, and no more. It
    builds the payload with `cls(**data)`, so a missing field raises `TypeError`
    in their process and an extra one does the same; this envelope is not a
    place to be generous in either direction.

    `result_claim` is how we ended the game in our own view. Stating it here is
    what lets the two peers detect a disagreement at audit time rather than
    discovering it in two contradictory reports, which void the game for both
    (rules 33-35).

    We used to send the bare list: the peer's validator rejected it, the reveal
    never arrived, and both sides recorded TAMPERED for a game neither had
    cheated in. Every in-memory test passed throughout, because the fake
    transport wrapped the list on the way past and the real one did not.
    """
    ledger.open_audit()
    payload = {
        "sender": sender,
        "records": ledger.audit_payload(),
        "result_claim": result_claim,
    }
    transport.send_audit(payload)
    return payload


def receive_reveal(transport: Any, timeout: float) -> AuditReport:
    """Re-hash whatever the peer revealed; silence is a failed audit, not a crash."""
    reply = transport.receive_audit(timeout)
    if reply is None:
        # Silence is not forgery. `TAMPERED` is an accusation that voids the
        # game for the accused (rule 19), and an opponent who never answered
        # has proved nothing except that they stopped talking — which the end
        # reason already records. We reached this from a *disagreement*, not a
        # forgery: they were still waiting for a move while we thought the game
        # was over, so they never got as far as revealing anything.
        return AuditReport(
            passed=False,
            skipped=True,
            errors=["opponent revealed nothing before the deadline"],
        )
    records = reply.get("records") if isinstance(reply, dict) else reply
    report = audit_records(records)
    claim = str(reply.get("result_claim", "") or "") if isinstance(reply, dict) else ""
    kept = [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []
    return replace(report, their_claim=claim, their_records=kept)


def exchange_audit(
    ledger: CommitLedger,
    transport: Any,
    timeout: float = 30.0,
    sender: str = "",
    result_claim: str = "",
) -> AuditReport:
    """Reveal ours, verify theirs, and report on theirs.

    Ours goes first unconditionally. Withholding our nonces until we have seen
    theirs would be indistinguishable, from their side, from preparing to
    forge — and rule 18 only protects a nonce until the audit, not through it.
    """
    send_reveal(ledger, transport, sender, result_claim)
    report = receive_reveal(transport, timeout)
    # The agreement the protocol actually affords: each side states how it
    # thinks the mini-game ended, inside the audit envelope. A contradiction
    # here is what rules 33-35 void both teams for, and it is far better known
    # now — while both agents are still connected — than after the lecturer
    # compares two emailed reports. An absent claim is not a dispute: an
    # opponent who reveals nothing has said nothing to disagree with.
    if report.their_claim and result_claim and report.their_claim != result_claim:
        return replace(report, disputed=True)
    return report
