"""Decoding what the opponent said — deterministically first, LLM only if needed.

Order matters and it is not the obvious one. A keyword pass runs *before* any
model call because most hints are plainly worded ("heading north past the
bridge"), and a local parse is free, instant, and cannot hallucinate a direction
the opponent never claimed. The model is the fallback for genuinely ambiguous
prose, not the default.

Failure is a first-class outcome: an unparseable hint yields zero confidence,
which the belief engine treats as an identity update. Guessing would be worse
than silence — a fabricated direction poisons the belief map with false
certainty (FR-LLM-5).
"""

import json
import re
from typing import Any

# `parse_locally` and its keyword table moved to the domain, so `turn_ingress`
# can read an opponent's words without importing the llm layer — book rule 25,
# enforced structurally by `test_the_domain_never_imports_an_llm_provider`.
# Re-exported here because callers (and tests) already import them from this
# module, and the model-reply parser below still uses them.
from ..domain.hint_evidence import (  # noqa: F401
    DIRECTION_WORDS,
    HintClaim,
    _words,
    parse_locally,
)

# A hint naming a direction is worth acting on; one that only names a landmark
# is weaker evidence, and credibility weighting downstream scales both.
DIRECTION_CONFIDENCE = 0.75
LANDMARK_CONFIDENCE = 0.5
NEGATION_WORDS = ("not", "never", "nowhere", "away from", "no longer")


def local_confidence(claim: HintClaim, text: str) -> float:
    """How much the keyword pass trusts its own reading."""
    if not claim.is_informative:
        return 0.0
    lowered = (text or "").lower()
    # "I did NOT go north" claims the opposite of what the keyword suggests, so
    # the local pass steps back and lets the model decide.
    if any(marker in lowered for marker in NEGATION_WORDS):
        return 0.2
    return DIRECTION_CONFIDENCE if claim.direction is not None else LANDMARK_CONFIDENCE


def parse_model_reply(reply: str, landmarks: dict[str, tuple[int, int]] | None = None) -> tuple[HintClaim, float]:
    """Read the model's JSON answer, tolerating the ways models wrap it."""
    payload = extract_json(reply)
    if payload is None:
        return HintClaim(text=reply or ""), 0.0
    raw_direction = str(payload.get("direction") or "").lower()
    direction = DIRECTION_WORDS.get(raw_direction)
    named: list[tuple[int, int]] = []
    for name in payload.get("landmarks") or []:
        cell = (landmarks or {}).get(str(name))
        if cell is not None:
            named.append(cell)
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    claim = HintClaim(direction=direction, landmark_cells=tuple(named), text=reply or "")
    return claim, max(0.0, min(1.0, confidence))


def extract_json(reply: str) -> dict[str, Any] | None:
    """Find the JSON object in a reply that may be fenced or chatty."""
    if not reply:
        return None
    candidate = reply.strip()
    fenced = re.search(r"\{.*\}", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(0)
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
