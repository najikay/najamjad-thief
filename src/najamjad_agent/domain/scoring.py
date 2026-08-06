"""Scoring: the fixed Appendix F table, plus series aggregation and the tie rule.

All five score values are *fixed* by Appendix F Table 17 — a peer proposing
different numbers is not negotiating, it is breaking the book, so the table is
validated on load rather than trusted.
"""

from dataclasses import dataclass

from ..constants import EndReason, Role, is_technical

# Appendix F Table 17 (fixed): capture 20/5, survival 5/10, tie 2, technical 0/0.
FIXED_SCORES = {
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "tie_score": 2,
}
TECHNICAL_LOSS_SCORE = 0


@dataclass(frozen=True)
class ScoreTable:
    """Validated per-match score values."""

    capture_cop: int
    capture_thief: int
    survival_cop: int
    survival_thief: int
    tie_score: int

    @classmethod
    def from_config(cls, config: dict) -> "ScoreTable":
        """Read the `scoring` block, rejecting any deviation from Appendix F."""
        section = config["scoring"]
        for key, expected in FIXED_SCORES.items():
            if int(section[key]) != expected:
                raise ValueError(f"{key} is fixed at {expected} by Appendix F; got {section[key]}")
        return cls(**{key: int(section[key]) for key in FIXED_SCORES})

    def score_subgame(self, end_reason: EndReason) -> dict[Role, int]:
        """Points for one mini-game, keyed by role."""
        if end_reason is EndReason.CAPTURE:
            return {Role.COP: self.capture_cop, Role.THIEF: self.capture_thief}
        if end_reason is EndReason.SURVIVAL:
            return {Role.COP: self.survival_cop, Role.THIEF: self.survival_thief}
        # Every other ending (timeout, tamper, quit) is a technical loss: the
        # book zeroes BOTH sides so neither profits from killing the protocol.
        return {Role.COP: TECHNICAL_LOSS_SCORE, Role.THIEF: TECHNICAL_LOSS_SCORE}


@dataclass(frozen=True)
class SeriesResult:
    """Aggregate of a full series, shaped for the `result_*.json` report."""

    total_score: dict[str, int]
    sub_games_won: dict[str, int]
    ties: int
    winner_group: str | None
    series_tie: bool
    tie_award: int | None = None
    #: Mini-games that ended off the board (timeout, forfeit, quit). Counted
    #: separately because they score 0/0 for both sides, which looks exactly
    #: like a draw and is not one — reporting them as ties described three
    #: unfinished games as three draws in a graded artifact.
    technical: int = 0


def aggregate_series(sub_games: list[dict], groups: tuple[str, str], tie_score: int) -> SeriesResult:
    """Aggregate per-mini-game scores into the series result.

    Each entry of `sub_games` maps group name -> points for that mini-game.
    `total_score` always reports the true accumulated points; an equal total
    sets `series_tie` with `tie_award` = the book's tie score for both teams
    (book PAGE 87), leaving `winner_group` null as the golden report expects.
    """
    totals = dict.fromkeys(groups, 0)
    wins = dict.fromkeys(groups, 0)
    ties = 0
    technical = 0
    for scores in sub_games:
        for group in groups:
            totals[group] += int(scores.get(group, 0))
        equal = scores.get(groups[0], 0) == scores.get(groups[1], 0)
        if equal and is_technical(scores.get("end_reason")):
            # Scored 0/0 for both, so the scores are equal — but nobody drew.
            # Counting it as a tie made our own artifact report `"ties": 3`
            # about a series in which three mini-games never finished.
            technical += 1
        elif equal:
            ties += 1
        else:
            wins[max(groups, key=lambda group: scores.get(group, 0))] += 1
    if totals[groups[0]] == totals[groups[1]]:
        return SeriesResult(totals, wins, ties, None, True, tie_score, technical)
    winner = max(groups, key=lambda group: totals[group])
    return SeriesResult(totals, wins, ties, winner, False, None, technical)
