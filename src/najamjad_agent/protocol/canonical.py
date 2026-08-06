"""Canonical JSON — the one byte-format both peers must agree on.

Every hash in the game is taken over this encoding, so it is pinned here and
nowhere else: sorted keys (order-independent), no whitespace, and
`ensure_ascii=False` so a hint written in Hebrew or with an emoji hashes to the
same bytes on both machines.

Verified byte-compatible with the lecturer's reference implementation against
all 19 records of the sample log (`tests/goldens/artifacts/log_*.json`) — a
mismatch here would mean a technical loss (book rule 19), so it is golden-tested
rather than assumed.
"""

import json
from typing import Any

SEPARATORS = (",", ":")


def canonical_json(payload: Any) -> str:
    """Serialize `payload` to the game's canonical string form."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=SEPARATORS)


def canonical_bytes(payload: Any) -> bytes:
    """UTF-8 bytes of the canonical form — the exact input to SHA-256."""
    return canonical_json(payload).encode("utf-8")


#: The release's **second** serialization, used by exactly one thing: the
#: settlement consensus signature. `json.dumps` defaults — `", "` and `": "` —
#: rather than our compact separators. It lives here so canonicalisation stays
#: pinned to one module (`test_canonicalisation_is_pinned_in_one_module`), and
#: because a second form that is *not* written down beside the first is a form
#: someone will eventually "fix".
SPACED_SEPARATORS = (", ", ": ")


def spaced_json(payload: Any) -> str:
    """The settlement form: sorted keys, raw UTF-8, default spacing.

    Not interchangeable with `canonical_json`. The two produce different bytes
    and therefore different digests for the same object, which is the whole
    reason `reporting/consensus.py` exists — a team signing the compact form
    fails settlement against a team signing this one, and neither can see why.
    See `vectors/report_consensus.json` in the published interop kit for the
    counter-example digests we assert against.
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=SPACED_SEPARATORS)
