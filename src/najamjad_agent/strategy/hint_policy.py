"""When to lie — the only deception channel in the game.

Scent cannot be faked (book PAGE 22), so the verbal hint is the entire deception
surface. That makes lying a *budget*, not a habit: every lie an opponent catches
permanently devalues everything we say afterwards, because their credibility
coefficient drops and never fully recovers within a series.

Hence the shape of this policy:

* **Cheap truths early.** Truthful hints in the opening cost almost nothing
  (the opponent has little belief to spoil) and buy credibility we spend later.
* **Lies at the moments that decide games.** When the cop is closing or the
  survival threshold is near, a believed lie is worth several turns of running.
* **Never tell a refutable lie.** A lie our own scent field immediately
  contradicts does not merely fail — it burns credibility for nothing, which is
  strictly worse than having said something true.
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import Move
from ..domain.hint_evidence import HintClaim, scent_consistency
from ..domain.params import Position

# Below this trust level a lie is unlikely to be believed, so it is not worth
# spending; above it, lies land. Deliberately not 0.5 — an opponent who half
# trusts us can still be moved by a well-timed claim.
MIN_TRUST_TO_LIE = 0.35
# Fraction of a mini-game treated as the opening, where truths are cheap.
OPENING_FRACTION = 0.3
# Danger radius that makes a moment "high value" for the thief.
CLOSE_PURSUIT = 3


@dataclass
class HintPolicy:
    """Chooses truth or lie, and refuses lies our own scent would refute."""

    max_lies: int = 6
    lies_told: int = 0
    lies_caught: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def budget_left(self) -> int:
        """Lies still available this mini-game."""
        return max(0, self.max_lies - self.lies_told)

    def choose_intent(
        self,
        step: int,
        max_steps: int,
        opponent_trust: float,
        pressure: float = 0.0,
    ) -> str:
        """Decide whether this turn's hint should be true or false.

        `pressure` is how badly we need the lie to land (0 = quiet turn, 1 =
        the moment that decides the game).
        """
        if self.budget_left <= 0:
            return "truth"
        if opponent_trust < MIN_TRUST_TO_LIE:
            # They no longer believe us; a lie now is wasted breath, and telling
            # the truth is how credibility is rebuilt.
            return "truth"
        if step <= max(1, int(max_steps * OPENING_FRACTION)) and pressure < 0.5:
            return "truth"
        return "lie" if pressure >= 0.5 else "truth"

    def pressure_for_thief(self, distance_to_cop: int, steps_survived: int, threshold: int) -> float:
        """How much this turn matters: close pursuit or a nearly-won game."""
        danger = max(0.0, 1.0 - distance_to_cop / max(1, CLOSE_PURSUIT))
        endgame = steps_survived / max(1, threshold)
        return min(1.0, max(danger, endgame))

    def plausible(
        self,
        claim: HintClaim,
        own_scent: dict[Position, float],
        own_position: Position,
    ) -> bool:
        """Reject a lie our own trail visibly contradicts.

        A refuted lie is worse than a truth: it costs credibility and buys
        nothing (book PAGE 46 shows exactly this being caught).
        """
        verdict = scent_consistency(claim, own_scent, own_position)
        return verdict != "refuted"

    def choose_lie_direction(
        self,
        legal: tuple[Move, ...],
        actual: Move,
        own_scent: dict[Position, float],
        own_position: Position,
    ) -> Move | None:
        """Pick a misdirection that our scent does not immediately refute."""
        for candidate in legal:
            if candidate is actual or candidate is Move.STAY:
                continue
            claim = HintClaim(direction=candidate)
            if self.plausible(claim, own_scent, own_position):
                return candidate
        return None

    def record(self, intent: str, believed: bool | None = None) -> None:
        """Note what we said and, when known, whether it was swallowed."""
        if intent == "lie":
            self.lies_told += 1
            if believed is False:
                self.lies_caught += 1
        self.history.append({"intent": intent, "believed": believed})

    def reset_for_new_game(self) -> None:
        """Budgets are per mini-game; credibility is not (that is the opponent's)."""
        self.lies_told = 0
        self.lies_caught = 0
        self.history.clear()
