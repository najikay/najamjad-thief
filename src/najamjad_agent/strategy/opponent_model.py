"""What we learn about one opponent — genuine online learning, sized to the data.

This is the project's learning component, and it is deliberately *small*. Across
a series we observe roughly 210 opponent turns (35 steps x 6 mini-games), which
is ample for a handful of parameters and nowhere near enough for a policy with
thousands. So we learn exactly what the data supports:

* **credibility** — how often their hints survive comparison with their scent;
* **movement tendencies** — which directions they favour, as a prior for the
  belief engine's motion model;
* **aggression** — how directly they close or flee, which tells us whether to
  expect interception or trailing.

Updates are exponentially weighted, so recent evidence dominates without
discarding history — an opponent who lied early and tells the truth later is
tracked, not permanently condemned.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..constants import Move
from ..protocol.canonical import canonical_json

# Weight of each new observation. High enough to adapt inside one mini-game,
# low enough that a single fluke does not rewrite the model.
LEARNING_RATE = 0.2
NEUTRAL_CREDIBILITY = 0.5


@dataclass
class OpponentModel:
    """Everything we have learned about one team, across a whole series."""

    group_id: str
    credibility: float = NEUTRAL_CREDIBILITY
    hints_seen: int = 0
    hints_refuted: int = 0
    move_counts: dict[str, int] = field(default_factory=dict)
    directness: float = 0.5
    observations: int = 0

    @property
    def refute_rate(self) -> float:
        """Share of their checkable hints that their own scent contradicted."""
        return self.hints_refuted / self.hints_seen if self.hints_seen else 0.0

    def record_hint(self, verdict: str) -> float:
        """Fold one scent-vs-claim verdict into their credibility.

        "unknown" deliberately changes nothing: an unverifiable hint is not
        evidence of honesty, and treating it as such would let an opponent
        rebuild trust by saying nothing checkable.
        """
        if verdict == "unknown":
            return self.credibility
        self.hints_seen += 1
        target = 1.0 if verdict == "consistent" else 0.0
        if verdict == "refuted":
            self.hints_refuted += 1
        self.credibility += LEARNING_RATE * (target - self.credibility)
        self.credibility = min(1.0, max(0.0, self.credibility))
        return self.credibility

    def record_move(self, move: Move | str, closed_distance: bool | None = None) -> None:
        """Note a movement tendency and whether they moved decisively."""
        key = move.value if isinstance(move, Move) else str(move)
        self.move_counts[key] = self.move_counts.get(key, 0) + 1
        self.observations += 1
        if closed_distance is not None:
            target = 1.0 if closed_distance else 0.0
            self.directness += LEARNING_RATE * (target - self.directness)
            self.directness = min(1.0, max(0.0, self.directness))

    def movement_prior(self) -> dict[str, float]:
        """Normalised direction preferences, for the belief motion model."""
        total = sum(self.move_counts.values())
        if not total:
            return {}
        return {move: count / total for move, count in self.move_counts.items()}

    def favours_staying(self) -> bool:
        """True when this opponent stalls more than a quarter of their turns.

        A staller is playing for the survival clock, which changes how we spend
        barriers: cornering beats chasing against a defensive thief.
        """
        return self.movement_prior().get(Move.STAY.value, 0.0) > 0.25

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form for the match workspace."""
        return {
            "group_id": self.group_id,
            "credibility": round(self.credibility, 4),
            "hints_seen": self.hints_seen,
            "hints_refuted": self.hints_refuted,
            "move_counts": dict(self.move_counts),
            "directness": round(self.directness, 4),
            "observations": self.observations,
        }

    def save(self, directory: Path) -> Path:
        """Persist to `matches/<opponent>/opponent_model.json`."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "opponent_model.json"
        path.write_text(canonical_json(self.as_dict()), encoding="utf-8")
        return path

    @classmethod
    def load(cls, directory: Path, group_id: str) -> "OpponentModel":
        """Reload what we knew, or start neutral against a new team."""
        path = directory / "opponent_model.json"
        if not path.exists():
            return cls(group_id=group_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})
