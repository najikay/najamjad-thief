"""Re-verification of a log, step by step (book rule 20).

The hashing itself lives in `domain.crypto` and the per-step verdict logic in
`domain.audit` — this module deliberately adds neither. Two implementations of
the same hash is how a replay viewer ends up disagreeing with the audit that
already ran, and then nobody knows which one to believe.

What this adds is *localisation*: which step failed, and what the viewer should
show beside it. A verdict of TAMPERED without pointing at the step is an
accusation nobody can check.
"""

from dataclasses import dataclass
from typing import Any

from ..domain.audit import AuditReport, audit_records
from ..domain.crypto import commit_of, verify
from .loader import load_document, load_records


@dataclass(frozen=True)
class StepVerdict:
    """One step's verification outcome, ready to render."""

    index: int
    step: int
    verified: bool
    commit: str
    recomputed: str
    reason: str = ""


@dataclass(frozen=True)
class ReplayResult:
    """The whole log's verdict plus everything the viewer needs."""

    report: AuditReport
    steps: list[StepVerdict]
    records: list[dict[str, Any]]
    document: dict[str, Any]

    @property
    def banner(self) -> str:
        """`Verified OK` or `TAMPERED` — the mandatory screenshot (rule 20)."""
        return self.report.banner

    @property
    def passed(self) -> bool:
        """Whether every step re-hashed to its stored commit."""
        return self.report.passed

    @property
    def failed_indices(self) -> list[int]:
        """Positions the viewer must highlight."""
        return [step.index for step in self.steps if not step.verified]

    @property
    def void(self) -> bool:
        """Rule 19: a proven forgery voids the game for its author."""
        return not self.report.passed and not self.report.skipped


def _step_number(record: dict[str, Any], index: int) -> int:
    """The record's own step number, falling back to its position."""
    payload = record.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("step"), int):
        return payload["step"]
    return index


def _verdict(record: dict[str, Any], index: int) -> StepVerdict:
    """Re-hash one record and describe the outcome."""
    step = _step_number(record, index)
    payload, nonce, commit = record.get("payload"), record.get("nonce"), record.get("commit")
    if not isinstance(payload, dict) or not isinstance(nonce, str) or not isinstance(commit, str):
        return StepVerdict(index, step, False, str(commit), "", "record is malformed")
    if not commit:
        return StepVerdict(index, step, False, commit, "", "no commitment stored")
    # `verify` compares with `compare_digest`; a plain `==` here would leak
    # timing, and a repo meta-test refuses one anywhere in the tree.
    verified = verify(payload, nonce, commit)
    recomputed = commit_of(payload, nonce)
    reason = "" if verified else "the revealed payload does not produce the stored commit"
    return StepVerdict(index, step, verified, commit, recomputed, reason)


def verify_log(source: Any) -> ReplayResult:
    """Load a log and re-verify every step in it.

    The aggregate verdict comes from `audit_records`, the same function that
    decides a live game, so the viewer can never disagree with the audit.
    """
    document = load_document(source)
    records = load_records(document)
    return ReplayResult(
        report=audit_records(records),
        steps=[_verdict(record, index) for index, record in enumerate(records)],
        records=records,
        document=document,
    )
