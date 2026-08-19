"""A split series has two HEADs, and each row must name the one that played it.

T-2710. `sub_game_rows` read a single `git_commit()` at filing time and wrote it
on all six rows. In a split series the filer is one of two checkouts, so it
stamped its own commit over the three mini-games its sibling had played: the
2026-08-17 MOAAMOHA practice attributed our thief's games 1/3/5 to the cop
repo's `dcec9ee`, while their own report — built from our per-window step-0 —
had the pair right. Rule 53 asks which code played a game, so half our answers
were wrong in the binding document.

The value now rides on the game record, written when the mini-game is
remembered, and `write_partial` carries the sibling's half verbatim.
"""

from najamjad_agent.reporting.result_blocks import sub_game_rows

THIEF_HEAD = "56a641582c16657e3ccbc5cebb4dcdbaa330f66a"
COP_HEAD = "dcec9ee59a60bc992f874df2f248760c3e720563"
GROUPS = ("najamjad", "MOAAMOHA")


class Outcome:
    """Just the fields `sub_game_rows` reads off a scored mini-game."""

    def __init__(self, our_score: int, their_score: int) -> None:
        self.our_score = our_score
        self.their_score = their_score


def game(number: int, role: str, commit: str | None) -> dict:
    row = {"sub_game": number, "role": role, "end_reason": "capture",
           "audit": "Verified OK", "tokens": 0}
    if commit is not None:
        row["our_commit"] = commit
    return row


def test_each_window_carries_the_commit_of_the_process_that_played_it() -> None:
    """The defect: one filer's HEAD on rows it did not play."""
    games = [game(1, "thief", THIEF_HEAD), game(2, "police", COP_HEAD),
             game(3, "thief", THIEF_HEAD)]
    outcomes = [Outcome(5, 20), Outcome(20, 5), Outcome(10, 5)]

    rows = sub_game_rows(games, outcomes, GROUPS, "MOAAMOHA-vs-najamjad")

    stamped = [row["github_commit"]["najamjad"] for row in rows]
    assert stamped == [THIEF_HEAD, COP_HEAD, THIEF_HEAD]
    assert len(set(stamped)) == 2, "a split series must not collapse to one HEAD"


def test_a_half_without_the_field_still_files() -> None:
    """An unsplit run, and any half written before the field existed.

    The fallback must stay: filing is the one step whose failure rule 35 scores
    as not having played, so a missing key may never raise here.
    """
    rows = sub_game_rows([game(1, "thief", None)], [Outcome(5, 20)], GROUPS, "g")

    assert rows[0]["github_commit"]["najamjad"]
