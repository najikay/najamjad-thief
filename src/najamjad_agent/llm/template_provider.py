"""The offline sentence bank — the end of the chain, and a legitimate strategy.

The book is explicit that a full series can be played at zero tokens
(PAGE 67), so this is not a degraded mode to be ashamed of: it is the floor that
guarantees we always have something to say. It cannot raise, cannot time out,
and costs nothing.

Hints are composed from role-specific phrasings plus landmarks drawn from the
negotiated `map_area`, so the prose still sounds like the agreed setting. The
truth/lie mix comes from configuration rather than a hardcoded ratio — the
reference implementation lies a flat 40% of the time, which is exactly the sort
of predictable tell a good opponent learns to read.
"""

import random
from typing import Any

from .base import Completion
from .token_meter import Usage

LANDMARKS: dict[str, tuple[str, ...]] = {
    "New York": ("Times Square", "the Brooklyn Bridge", "Central Park", "the waterfront"),
    "London": ("the Thames", "Camden Market", "the Underground", "Hyde Park"),
    "Paris": ("the Seine", "Montmartre", "the old arcades", "the Latin Quarter"),
    "": ("the market", "the old bridge", "the north quarter", "the riverside"),
}
THIEF_LINES = (
    "Slipping past {landmark} while you look the wrong way.",
    "Still moving {direction} — {landmark} is behind me now.",
    "You will not find me anywhere near {landmark}.",
    "Taking the long way round by {landmark}.",
)
COP_LINES = (
    "Closing in near {landmark} — nowhere left to run.",
    "I have {landmark} covered; try heading {direction}.",
    "Every road past {landmark} is watched now.",
    "Working my way {direction} from {landmark}.",
)
DIRECTIONS = ("north", "south", "east", "west")


class TemplateProvider:
    """Deterministic, offline hint generation at zero token cost."""

    name = "template"
    free = True

    def __init__(
        self,
        map_area: str = "",
        lie_probability: float = 0.35,
        seed: int | None = None,
    ) -> None:
        """Configure the bank; `seed` makes output reproducible in tests."""
        if not 0.0 <= lie_probability <= 1.0:
            raise ValueError("lie_probability must lie between 0 and 1")
        self.map_area = map_area
        self.lie_probability = lie_probability
        self._random = random.Random(seed)

    def landmarks(self) -> tuple[str, ...]:
        """Vocabulary for the negotiated arena, with a generic fallback."""
        return LANDMARKS.get(self.map_area, LANDMARKS[""])

    def compose(self, role: str, hint_max_words: int = 15) -> dict[str, Any]:
        """Build one hint plus the intent that will be sealed with it."""
        lines = THIEF_LINES if role == "thief" else COP_LINES
        text = self._random.choice(lines).format(
            landmark=self._random.choice(self.landmarks()),
            direction=self._random.choice(DIRECTIONS),
        )
        words = text.split()
        if len(words) > hint_max_words:
            text = " ".join(words[:hint_max_words])
        verdict = "lie" if self._random.random() < self.lie_probability else "truth"
        return {"message": text, "verdict": verdict, "reasoning": "template bank"}

    def complete(self, system: str, user: str, max_tokens: int = 0) -> Completion:
        """Provider-contract entry point; `user` carries the role hint."""
        role = "thief" if "thief" in user.lower() else "police"
        composed = self.compose(role)
        return Completion(
            text=composed["message"],
            provider=self.name,
            model="template-bank",
            usage=Usage(),
            raw=composed,
        )

    def healthy(self) -> bool:
        """Always true — this is the floor the whole chain rests on."""
        return True
