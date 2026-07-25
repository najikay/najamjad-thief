"""Treating the opponent's words as hostile input, because they are.

Every hint we receive is attacker-controlled text that we then feed to a model
to decode. A team that reads our public repository knows exactly what that
prompt looks like, and the payoff for subverting it is concrete: make our parser
report a confident wrong direction and our belief map chases a ghost for the
rest of the game.

The defence is layered, and the outer layers do not involve a model at all:

1. **Contractual truncation.** The hint word cap is an agreed term, so a
   500-word "hint" is already a protocol violation. Cutting to the cap removes
   most payload room before anything is interpreted.
2. **Delimiting.** The text is quoted into a fenced block and the system prompt
   says the block is data, never instructions.
3. **Detection.** Recognisable instruction-injection phrasing is flagged; we
   still parse, but the claim's confidence is discounted and an event is
   emitted, because an opponent trying this is itself information.
4. **Whitelist output.** Downstream, `parse_model_reply` accepts only known
   direction words, known landmarks and a clamped confidence — so even a fully
   subverted model cannot inject an arbitrary claim.

Layer 4 is what makes this robust: the blast radius of a successful injection is
bounded by a five-value enum.
"""

import re
from dataclasses import dataclass

# Phrasings that only appear when someone is talking to a model rather than an
# opponent. A genuine hint has no reason to contain any of them.
INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+|the\s+|your\s+)?(?:previous|prior|above)\b", re.I),
    re.compile(r"\bdisregard\s+(?:all\s+|the\s+|your\s+)?(?:previous|prior|above|instructions)\b", re.I),
    re.compile(r"\b(?:system|assistant|user)\s*:", re.I),
    re.compile(r"\byou\s+are\s+(?:now|a|an)\b", re.I),
    re.compile(r"\bnew\s+instructions?\b", re.I),
    re.compile(r"\brespond\s+with\b|\breply\s+with\b|\boutput\s+(?:only|exactly)\b", re.I),
    re.compile(r"\bconfidence\"?\s*[:=]", re.I),
    re.compile(r"\{[^}]*\"(?:direction|confidence|landmarks)\"", re.I),
    re.compile(r"```"),
    re.compile(r"</?[a-z_]+>"),
)
# Confidence multiplier applied when the text looks like an attack.
SUSPICION_DISCOUNT = 0.25
MAX_CHARS = 400


@dataclass
class SanitisedHint:
    """An opponent hint made safe to interpret."""

    text: str
    suspicious: bool
    reasons: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def confidence_multiplier(self) -> float:
        """How much to trust any claim extracted from this text."""
        return SUSPICION_DISCOUNT if self.suspicious else 1.0


def sanitise_hint(raw: str, word_cap: int = 15) -> SanitisedHint:
    """Make an inbound hint safe to place in a prompt.

    Truncation is justified by the contract rather than by paranoia: both teams
    agreed a word cap, so anything beyond it is not a hint we owe interpretation.
    """
    text = (raw or "").strip()
    reasons: list[str] = []

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        reasons.append(f"exceeded {MAX_CHARS} characters")

    words = text.split()
    truncated = len(words) > word_cap
    if truncated:
        text = " ".join(words[:word_cap])
        reasons.append(f"exceeded the agreed {word_cap}-word cap")

    # Control characters and newlines are how a payload escapes its block.
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    matched = [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(raw or "")]
    if matched:
        reasons.append(f"instruction-like phrasing ({len(matched)} pattern(s))")

    return SanitisedHint(
        text=text,
        suspicious=bool(matched),
        reasons=tuple(reasons),
        truncated=truncated,
    )


def fence(text: str) -> str:
    """Quote untrusted text so a model cannot mistake it for instructions."""
    safe = text.replace("<", "\\<").replace(">", "\\>")
    return f"<opponent_message>{safe}</opponent_message>"
