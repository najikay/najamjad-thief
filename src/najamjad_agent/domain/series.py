"""Series bookkeeping: 6 mini-games against one opponent, with role swaps.

Appendix F Table 18 fixes a series at 6 mini-games. Roles alternate so neither
team's grade depends on drawing the easier side, and each mini-game starts from
clean per-game state — a belief map or scent trail leaking across games would
be both wrong and unauditable.

The transport deliberately does *not* reset: the tunnel and MCP session persist
for the whole series (reconnecting between games is how A6 lost time).
"""

from dataclasses import dataclass, field

from ..constants import EndReason, Role
from .scoring import ScoreTable, SeriesResult, aggregate_series

MINI_GAMES_PER_SERIES = 6


def role_for(sub_game: int, first_role: Role) -> Role:
    """Alternate roles each mini-game, starting from `first_role`."""
    if sub_game < 1:
        raise ValueError("sub_game numbering starts at 1")
    swapped = (sub_game - 1) % 2 == 1
    if not swapped:
        return first_role
    return Role.THIEF if first_role is Role.COP else Role.COP


@dataclass
class SubGameOutcome:
    """The scored result of one finished mini-game."""

    sub_game: int
    role: Role
    end_reason: EndReason
    our_score: int
    their_score: int
    steps: int = 0
    audit_passed: bool = True


@dataclass
class SeriesTracker:
    """Accumulates mini-game outcomes into the series result."""

    our_group: str
    their_group: str
    table: ScoreTable
    first_role: Role = Role.COP
    total_games: int = MINI_GAMES_PER_SERIES
    outcomes: list[SubGameOutcome] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True once every mini-game of the series has been played."""
        return len(self.outcomes) >= self.total_games

    @property
    def next_sub_game(self) -> int:
        """1-based number of the mini-game about to be played."""
        return len(self.outcomes) + 1

    def next_role(self) -> Role:
        """Our role in the upcoming mini-game."""
        return role_for(self.next_sub_game, self.first_role)

    def record(
        self,
        end_reason: EndReason,
        role: Role,
        steps: int = 0,
        audit_passed: bool = True,
    ) -> SubGameOutcome:
        """Score one finished mini-game and add it to the series."""
        effective = EndReason.TAMPER_FORFEIT if not audit_passed else end_reason
        scores = self.table.score_subgame(effective)
        other = Role.THIEF if role is Role.COP else Role.COP
        outcome = SubGameOutcome(
            sub_game=self.next_sub_game,
            role=role,
            end_reason=effective,
            our_score=scores[role],
            their_score=scores[other],
            steps=steps,
            audit_passed=audit_passed,
        )
        self.outcomes.append(outcome)
        return outcome

    def result(self) -> SeriesResult:
        """Aggregate every recorded mini-game into the series result."""
        # `end_reason` travels with the scores because a technical ending
        # scores 0/0 for both sides, and equal scores are how a tie is detected —
        # so without it every abandoned game was aggregated as a draw.
        rows = [
            {
                self.our_group: outcome.our_score,
                self.their_group: outcome.their_score,
                "end_reason": outcome.end_reason.value,
            }
            for outcome in self.outcomes
        ]
        return aggregate_series(rows, (self.our_group, self.their_group), self.table.tie_score)
