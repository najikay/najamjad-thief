"""The last check before a hint leaves us.

Two book rules meet here and both are unforgiving. Rule 26 requires free natural
language; rule 27 forbids a numeric-coordinate protocol — and a model that
helpfully writes "I'm at (3,4)" would break the game's whole premise while
sounding perfectly cooperative. The word cap is an agreed term, so exceeding it
is a contract breach rather than a style issue.

Everything here runs *after* generation, on whatever the model produced, because
a prompt instruction is a request and a guard is a guarantee.
"""

import re
from dataclasses import dataclass

# "(3,4)", "3,4", "row 3 col 4", "at 3 4" — the shapes a helpful model reaches for.
COORDINATE_PATTERNS = (
    re.compile(r"\(\s*\d+\s*[,;]\s*\d+\s*\)"),
    re.compile(r"\b\d+\s*[,;]\s*\d+\b"),
    re.compile(r"\b(?:row|col|column|cell|square|coord\w*)\s*[:=]?\s*\d+", re.IGNORECASE),
    re.compile(r"\b[a-h]\s*-?\s*[1-9]\b", re.IGNORECASE),
)
VALID_INTENTS = ("truth", "lie")


@dataclass
class GuardResult:
    """The vetted hint plus what had to be changed."""

    text: str
    intent: str
    problems: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        """True when the model's output needed no intervention."""
        return not self.problems


def strip_coordinates(text: str) -> tuple[str, bool]:
    """Remove coordinate-like fragments; report whether any were found."""
    cleaned = text
    for pattern in COORDINATE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;-")
    return cleaned, cleaned != text


def enforce_word_cap(text: str, limit: int) -> tuple[str, bool]:
    """Trim to the agreed word limit, reporting whether it was over."""
    words = text.split()
    if len(words) <= limit:
        return text, False
    return " ".join(words[:limit]), True


def looks_like_machinery(text: str) -> bool:
    """Whether this is a model's plumbing rather than a sentence.

    A hint is free natural language the opponent reads. When a provider answers
    with JSON — or with a JSON reply that was truncated in transit — we used to
    seal it and send it: mini-game 2 against Amjad carries the literal hint
    `{"message": "New`, which is now in an audited log a grader reads, and in
    our own sealed record where it cannot be edited out.

    Nothing upstream catches it. `strip_coordinates` removes digits and
    `enforce_word_cap` counts words; neither has any opinion about syntax, and
    a three-token fragment passes a fifteen-word cap comfortably.

    Deliberately narrow. A colon is ordinary English — "Heading north: the park
    is behind me" must survive — so only a leading brace or bracket, or a
    quoted key immediately followed by a colon, counts as machinery.
    """
    stripped = (text or "").strip()
    return bool(stripped.startswith(("{", "[")) or re.search(r'"\s*:', stripped))


def guard_hint(
    text: str,
    intent: str,
    hint_max_words: int = 15,
    fallback: str = "Still moving through the streets.",
) -> GuardResult:
    """Vet one generated hint against every rule before it is sealed."""
    problems: list[str] = []
    candidate = (text or "").strip()
    if not candidate:
        problems.append("empty hint replaced with a neutral line")
        candidate = fallback
    if looks_like_machinery(candidate):
        problems.append("model syntax leaked into the hint; neutral line used")
        candidate = fallback
    candidate, had_coordinates = strip_coordinates(candidate)
    if had_coordinates:
        problems.append("coordinates removed (book rule 27 forbids numeric protocols)")
    candidate, was_long = enforce_word_cap(candidate, hint_max_words)
    if was_long:
        problems.append(f"trimmed to the agreed {hint_max_words}-word limit")
    if not candidate.strip():
        problems.append("nothing survived vetting; neutral line used")
        candidate = fallback
    chosen = intent if intent in VALID_INTENTS else "truth"
    if chosen != intent:
        problems.append(f"intent {intent!r} is not truth/lie; sealed as truth")
    return GuardResult(text=candidate, intent=chosen, problems=tuple(problems))
