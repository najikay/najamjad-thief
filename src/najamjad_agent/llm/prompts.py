"""Prompt builders — every instruction the model ever receives.

Kept in one module for three reasons: the guidelines require a prompt book
(§8.3) and this is its source of truth; a prompt that lives next to its caller
drifts silently; and the constraints here (word cap, no coordinates, strict JSON)
must be identical everywhere or the guards downstream start rejecting our own
output.

The prompts *ask* for the rules. `hint_guard` then *enforces* them — a model
that ignores an instruction must not be able to breach the contract.
"""

from typing import Any

from ..protocol.canonical import canonical_json

HINT_SYSTEM = """You are the {role} in a hidden-information pursuit game set in {arena}.
Speak in natural language only — never numbers, coordinates, grid references or
compass bearings with digits. Reply with at most {word_cap} words.

You may tell the truth or deliberately mislead. State which you did.

Reply with JSON only: {{"message": str, "verdict": "truth"|"lie", "reasoning": str}}"""

PARSE_SYSTEM = """You read an opponent's message in a pursuit game and extract what it claims.

Return JSON only:
{"direction": "north"|"south"|"east"|"west"|"stay"|null,
 "landmarks": [str],
 "confidence": 0.0-1.0}

Use null and an empty list when the message says nothing locational. Never guess:
a low confidence score is more useful to us than an invented direction."""

NEGOTIATE_SYSTEM = """You draft one short, courteous negotiation message to an opposing team.
State our position and our reasoning plainly. Do not concede anything marked as a
red line, and do not invent terms that are not listed.

Reply with prose only — the binding numbers travel in a structured block beside
your text, so never restate them as a list."""


def hint_prompt(
    role: str,
    arena: str,
    word_cap: int,
    intent: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """System and user prompt for one bluff or taunt."""
    system = HINT_SYSTEM.format(
        role="thief evading a pursuer" if role == "thief" else "police officer in pursuit",
        arena=arena or "an unnamed city",
        word_cap=word_cap,
    )
    intention = (
        "Mislead them about where you are." if intent == "lie" else "Say something true."
    )
    lines = [intention]
    if context:
        lines.append(f"Situation: {canonical_json(context)}")
    lines.append("Write the message now.")
    return system, "\n".join(lines)


def parse_prompt(message: str) -> tuple[str, str]:
    """System and user prompt for decoding an opponent's free text."""
    return PARSE_SYSTEM, f"Opponent said: {message!r}\nExtract the claim."


def negotiate_prompt(
    position: dict[str, Any],
    red_lines: dict[str, str],
    opponent: str = "the other team",
) -> tuple[str, str]:
    """System and user prompt for drafting a negotiation message.

    The numeric terms are passed as a structured block rather than asked for in
    prose: nothing binding may exist only in free text, where a model could
    round it or drop it.
    """
    user = "\n".join(
        [
            f"We are writing to {opponent}.",
            f"Our position: {canonical_json(position)}",
            f"Red lines we cannot move on: {canonical_json(red_lines)}",
            "Draft the message.",
        ]
    )
    return NEGOTIATE_SYSTEM, user


def prompt_catalogue() -> dict[str, str]:
    """Every system prompt, for the prompt book (guidelines §8.3)."""
    return {
        "hint": HINT_SYSTEM,
        "parse": PARSE_SYSTEM,
        "negotiate": NEGOTIATE_SYSTEM,
    }
