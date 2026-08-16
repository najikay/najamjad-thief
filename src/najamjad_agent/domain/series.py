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


def plays_window(sub_game: int, first_role: Role, our_role: Role) -> bool:
    """Whether *this process* holds the role that plays this mini-game.

    Book Appendix ה Table 7 rule 1 requires the cop's code and the thief's code
    to run in two completely separate processes, on pain of `כישלון מוחלט`. A
    series still alternates roles across its six mini-games, so with one
    process per role each of them plays only half of them: opening as thief
    means our thief process takes 1, 3 and 5 and our cop process takes 2, 4
    and 6, and neither has to ask the other which — the answer is a function of
    the agreed opening role and nothing else.

    `first_role` is therefore no longer "the role of whichever repo was
    launched". It is the role *the group* holds in mini-game 1, agreed with the
    opponent beforehand and configured identically in both repos; `our_role` is
    what this process is. They coincide in exactly one of the two processes.
    """
    return role_for(sub_game, first_role) is our_role


def split_roles(configured: str, our_role: Role) -> tuple[Role, Role | None]:
    """Resolve `(opening_role, our_role)` from the configured opening role.

    An empty setting means the roles are **not** split: one process plays all
    six windows, opening in whichever role it is, exactly as before. That is
    the pre-2026-08-15 behaviour and it stays the default so no test, harness
    or rehearsal changes underneath us.

    A value turns the split on, and it is the one thing the two processes must
    agree about: our group's role in mini-game 1. Both repos must be given the
    *same* value — `police` in both, or `thief` in both — because it describes
    the group, not the process. Disagreement is silent and expensive: both
    would claim mini-game 1 and neither would play 2, so it is echoed at
    startup for the operator to compare across the two terminals.

    `cop` is accepted alongside `police` because that is what everyone types.
    """
    text = (configured or "").strip().lower()
    if not text:
        return our_role, None
    return Role.COP if text == "cop" else Role(text), our_role


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
    #: Mini-games this process has advanced past, whether or not it played
    #: them. Numbering used to be `len(outcomes) + 1`, which was the same thing
    #: while one process played all six. Under one process per role it is not:
    #: our cop process skips 1, 3 and 5, and deriving the number from outcomes
    #: would have it announce mini-game 2 as mini-game 1 — two reports
    #: describing one match with different `sub_game_number`s, which rules
    #: 33-35 can void *both* teams for. The cursor counts windows; `outcomes`
    #: holds only games we actually played, which is exactly what the sibling
    #: merge needs to fill in.
    cursor: int = 0
    #: The role *this process* is, when the two roles run as two processes
    #: (book Appendix ה rule 1). `None` keeps the pre-split behaviour — one
    #: process plays all six windows — so every existing caller and test is
    #: unaffected until a run opts in.
    our_role: Role | None = None

    @property
    def is_complete(self) -> bool:
        """True once the series has passed its last mini-game."""
        return self.cursor >= self.total_games

    @property
    def next_sub_game(self) -> int:
        """1-based number of the mini-game about to be played."""
        return self.cursor + 1

    def skip(self) -> int:
        """Advance past a mini-game our sibling process is playing.

        Nothing is recorded: we did not witness it, and inventing a 0-0
        technical outcome for it would put a game we never saw into our own
        report as though it had been abandoned.
        """
        self.cursor += 1
        return self.cursor

    def advance_to_ours(self) -> int | None:
        """The number of the next mini-game *this process* plays.

        Skips the windows our sibling process holds, so the caller never has to
        know the split exists. Returns None once no windows of ours remain,
        which ends the series loop for this process while the sibling is still
        playing its own — the two exit independently and neither waits on the
        other, because waiting would be shared state by another name.
        """
        while not self.is_complete:
            sub_game = self.next_sub_game
            if self.our_role is None or plays_window(sub_game, self.first_role, self.our_role):
                return sub_game
            self.skip()
        return None

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
        self.cursor += 1
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
