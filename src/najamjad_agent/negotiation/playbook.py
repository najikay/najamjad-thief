"""Our negotiating position: what we open with, want, and will never accept.

Every negotiable Appendix F item gets a triple — default (the book's value),
preferred (what suits our strategy), and a red line. Encoding it as data rather
than judgement means a match can be negotiated quickly and consistently, and
that a proposal is evaluated the same way at 2am as at noon.

Red lines are principled, not stubborn:

* **Lowering any Appendix F minimum** is a rule breach, not a concession.
* **Numeric-coordinate hint protocols** are explicitly forbidden (rule 27).
* **The LLM-move exception** we decline — our edge is a deterministic engine, and
  accepting would hand the advantage to a team with a bigger model budget.
* **Skipping the audit** removes the only thing that makes honesty verifiable.
"""

from dataclasses import dataclass, field
from typing import Any

ACCEPT = "accept"
COUNTER = "counter"
REJECT = "reject"


@dataclass(frozen=True)
class Position:
    """Our stance on one negotiable term."""

    key: str
    default: Any
    preferred: Any
    floor: Any = None
    rationale: str = ""

    def acceptable(self, value: Any) -> bool:
        """Whether a proposed value is one we can sign."""
        if self.floor is None:
            return True
        try:
            return float(value) >= float(self.floor)
        except (TypeError, ValueError):
            return value == self.default


# Tables 13-15 and 18-19: every row we are allowed to move on.
POSITIONS: tuple[Position, ...] = (
    Position("grid_size", 7, 7, 7, "A larger board favours evasion; 7x7 keeps pursuit viable."),
    Position("max_barriers", 14, 14, 14, "More barriers help the cop; we play both roles equally."),
    Position("max_moves", 35, 35, 35, "Longer games favour the thief's survival win."),
    Position("survival_threshold", 35, 35, 35, "Must track max_moves or the ending is ambiguous."),
    Position("num_games", 6, 6, 6, "Fixed at 6 by Appendix F Table 18."),
    Position("hint_max_words", 15, 15, None, "Longer hints leak more; 15 is enough to bluff."),
    Position("map_area", "New York", "New York", None, "Shared landmark vocabulary aids parsing."),
    Position("axis_origin_corner", "top-left", "top-left", None, "Reference default; fewer bugs."),
    Position("axis_start_index", 0, 0, None, "Zero-based matches every implementation we have seen."),
    Position("response_timeout_sec", 30, 45, 30, "45s absorbs a tunnel hiccup without stalling play."),
    Position("watchdog_timeout_sec", 60, 90, 60, "Headroom over the response timeout."),
    Position("token_budget_per_series", 200_000, 200_000, None, "Ample; we use about a quarter."),
)

RED_LINES: dict[str, str] = {
    "numeric_hints": "hints must be free natural language (book rule 27)",
    "llm_moves": "movement stays deterministic Python (book rule 25; our strategic edge)",
    "skip_audit": "the mutual audit is what makes honesty verifiable (book rule 36)",
    "lower_minimum": "Appendix F minimums may be raised, never lowered (book rule 12)",
}


@dataclass
class Playbook:
    """Evaluates proposals and produces our opening terms."""

    positions: tuple[Position, ...] = POSITIONS
    red_lines: dict[str, str] = field(default_factory=lambda: dict(RED_LINES))

    def opening_terms(self) -> dict[str, Any]:
        """What we propose first: our preferred value for every term."""
        return {position.key: position.preferred for position in self.positions}

    def default_terms(self) -> dict[str, Any]:
        """The book's own values — our fallback when a peer wants no discussion."""
        return {position.key: position.default for position in self.positions}

    def position_for(self, key: str) -> Position | None:
        """Our stance on one term, if it is negotiable at all."""
        return next((item for item in self.positions if item.key == key), None)

    def evaluate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Score a peer's proposal into accept / counter / reject with reasons."""
        violations: list[str] = []
        counters: dict[str, Any] = {}
        for key, value in proposal.items():
            if key in self.red_lines and value:
                violations.append(f"{key}: {self.red_lines[key]}")
                continue
            position = self.position_for(key)
            if position is None:
                continue
            if not position.acceptable(value):
                violations.append(f"{key}={value}: {self.red_lines['lower_minimum']}")
            elif value != position.preferred:
                counters[key] = position.preferred
        if violations:
            return {"verdict": REJECT, "reasons": violations, "counter": {}}
        if counters:
            return {"verdict": COUNTER, "reasons": self._explain(counters), "counter": counters}
        return {"verdict": ACCEPT, "reasons": [], "counter": {}}

    def _explain(self, counters: dict[str, Any]) -> list[str]:
        """Human-readable rationale for each counter-proposal."""
        explained = []
        for key, value in counters.items():
            position = self.position_for(key)
            reason = position.rationale if position else ""
            explained.append(f"{key} -> {value}: {reason}".strip())
        return explained
