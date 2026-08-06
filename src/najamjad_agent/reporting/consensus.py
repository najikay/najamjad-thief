"""The settlement signature — and it is *not* our canonical form.

Everything else we hash uses the compact canonical JSON in `protocol/canonical`:
`separators=(",", ":")`, no spaces. The release's settlement signature does not.
It uses sorted keys and raw UTF-8 like everything else, but with the standard
library's **default** separators — `", "` and `": "` — and the digest is
computed *before* the signature key is inserted into the report it signs. The
serializer itself lives in `protocol/canonical.spaced_json`, so both forms sit
side by side in the one module that owns encoding.

Two forms, both correct, for different jobs. Using the wrong one here fails at
the single moment both teams must agree, which under rules 33-35 voids the match
for both of us. The published interop kit calls this out explicitly and supplies
the counter-example digests: for their two vectors we reproduce the spaced
signature *and* the compact hash that does not match it, so the divergence is
demonstrated rather than assumed.

Sourced from the reference `report_writer.py` and cross-checked on 2026-08-05
against `github.com/Imreec/copthief-league-protocol` `vectors/report_consensus.json`
(found by alonengel / anrbj666). Verified against their vectors, never imported.

**Not currently written into any artifact, and that is deliberate.** Two reasons,
both found by review after a first attempt put it into `result_<game_id>.json`:

* `ResultArtifact` is `extra="forbid"`, and the signature was inserted *after*
  `validate_egress` — so the bytes we emailed were the one artifact in the
  project that never passed validation, and a peer or grader parsing strictly
  would reject the whole report (rule 35). Exactly the inversion
  `PRD_reporting.md` exists to prevent.
* `docs/research/simulator-repo-digest.md` places this key in the reference's
  legacy Hebrew `logs/{role}_match.json`, **not** in the result artifact. We had
  put it in a file the reference does not carry it in.

**And it is not a cross-peer consensus value**, whatever its name suggests. A
first version of this docstring claimed it answered "is our report the same
report as theirs". It cannot: computed over a whole report it necessarily covers
per-peer fields — `github_commit`, token counts, `repositories`, which side we
listed first — so our digest and theirs differ by construction on every match.
It is a *self*-integrity hash: proof that a report has not been altered since we
signed it. `reporting/agreement.py` owns the genuinely symmetric value, hashing
only facts both peers compute identically.

What this module is for, then: reproducing the release's second byte format
exactly, so we can **verify an opponent's** signed report in a rules 33-35
dispute, and so we can produce one wherever the league later asks for it,
without anyone having to rediscover that the settlement form is spaced.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..protocol.canonical import spaced_json

#: The key the settlement signature is published under. Hebrew, because that is
#: what the reference writes and what the other teams will look for.
SIGNATURE_KEY = "חתימת_קונסנזוס_משותפת"


def settlement_body(report: dict[str, Any]) -> str:
    """The exact string that gets hashed: sorted keys, spaced, raw UTF-8.

    `ensure_ascii=False` matters as much here as anywhere else — this report is
    Hebrew-keyed, so escaping would change every byte of it.
    """
    return spaced_json(report)


def settlement_signature(report: dict[str, Any]) -> str:
    """SHA-256 of the spaced form, over the report *without* its signature.

    Any existing signature key is dropped first, which is what makes the value
    verifiable: a peer recomputes it by popping the key, re-serializing and
    re-hashing, and that only works if we signed the same thing they pop back
    to.
    """
    body = {key: value for key, value in report.items() if key != SIGNATURE_KEY}
    return hashlib.sha256(settlement_body(body).encode("utf-8")).hexdigest()


def sign_report(report: dict[str, Any]) -> dict[str, Any]:
    """The report with its settlement signature inserted (sign-then-insert)."""
    return {**report, SIGNATURE_KEY: settlement_signature(report)}


def verify_report(report: dict[str, Any]) -> bool:
    """Whether a signed report — ours or an opponent's — carries a good signature.

    Useful in a dispute: rules 33-35 void a match when two reports contradict,
    and the first question is whether theirs is internally consistent before
    anyone argues about whose numbers are right.
    """
    claimed = report.get(SIGNATURE_KEY)
    return isinstance(claimed, str) and claimed == settlement_signature(report)
