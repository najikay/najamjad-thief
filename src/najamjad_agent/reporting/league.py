"""The league fields a standings table reads, derived from shared facts.

Split from `result_blocks` when that file crossed its budget, and it earns a
module: these three fields are the only part of the result that describes the
*series in the league* rather than the game, and rule 38 judges two of them
on consistency between the two teams' files rather than on our own honesty.
"""

from __future__ import annotations

from typing import Any

#: The count keys a peer may declare. Ours has always been the first; the
#: league's readers look for the second, and a peer finding neither prints zero.
COUNT_KEYS = ("counted_matches_played", "counted_games_played")


def league_block(
    groups_block: dict[str, Any],
    counted: bool,
    groups: tuple[str, str] | None = None,
    winner: str | None = None,
    result: Any = None,
    rename: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The three template fields a league table reads, per group.

    Absent from our result until now, so a grader building standings from our
    file found nothing where the template says to look. They are outside every
    hash — the agreement digest covers the symmetric outcome only — but rule 38
    judges counted-match declarations on *mutual consistency between the two
    teams' files*, which makes a missing or wrong count a project-level matter
    rather than a cosmetic one.

    `games_played_including_this` counts the series being filed, so a counted
    match is the declared total plus one and a friendly is the total unchanged.
    Read from whichever spelling the peer declared, because assuming ours is
    exactly the bug this fixes.

    `diversity_reward_applied` is **derived, not claimed**: counted AND first
    meeting AND this group won. We emitted all-false first, reasoning that
    awarding ourselves a bonus was not ours to do — but a reward that follows
    from three shared facts is no more a claim than a score is, and emitting
    all-false would make the two counted files visibly disagree on a +10 line
    while every other difference between them is a declared per-side one. The
    conditional crowns whoever won, including the opponent.
    """
    if result is not None:
        # The tracker scores against its `"them"` placeholder until the
        # handshake names the opponent, so the winner needs the same relabelling
        # the score maps get — otherwise a defeat credits the reward to nobody.
        found = getattr(result, "winner_group", None)
        # A drawn series has no winner, and `None` is not a key: the relabel
        # only applies when there is a name to relabel.
        winner = (rename or {}).get(found, found) if isinstance(found, str) else None
    names = list(groups or tuple(groups_block)) or list(groups_block)
    played: dict[str, int] = {}
    met_before = False
    for name in names:
        block = dict(groups_block.get(name) or {})
        declared = next((int(block[key]) for key in COUNT_KEYS if key in block), 0)
        played[name] = declared + (1 if counted else 0)
        if [other for other in (block.get("opponents_already_counted") or []) if other in names]:
            met_before = True
    first_meeting = not met_before
    return {
        "games_played_including_this": played,
        "first_meeting_between_groups": first_meeting,
        "diversity_reward_applied": {
            name: bool(counted and first_meeting and winner == name) for name in names
        },
    }




def document_extras(
    rows: list[dict[str, Any]],
    agreed_sub_games: int,
    games: list[dict[str, Any]],
    emission: dict[str, str] | None,
) -> dict[str, Any]:
    """The self-describing extras every artifact carries beside its rows.

    **The series is the signed term; the rows are this document's.**
    `num_sub_games` was once the schema default (6) beside a result computed
    from rows played — a two-game match filing "six" — and the fix
    over-corrected to `len(rows)`, so a split-friendly half-document declared
    a three-game series against a signed term of six. anrbj666 audited
    exactly that (2026-08-22) and supplied the shape adopted here: declare
    the agreed series length, state how many rows this document carries, and
    say where the rest live. A counted filing merges all six rows, so there
    the numbers coincide and the note is not emitted.

    The timestamps fill the golden's empty strings: the first game's start
    and the last game's end are both on the records.
    """
    extra: dict[str, Any] = {"emission": emission} if emission else {}
    extra["num_sub_games"] = int(agreed_sub_games)
    extra["rows_in_this_document"] = len(rows)
    if len(rows) < agreed_sub_games:
        # The only path to a short document since the merge became the filing
        # rule is a sibling half that never appeared — the bestteam warm-up
        # (2026-08-24) mailed this note while the sibling was still playing,
        # and its old text falsely reassured the reader that another document
        # carried the missing rows. Name the anomaly instead: a reader must
        # see a flag, not a promise nobody verified.
        extra["rows_note"] = (
            f"INCOMPLETE: {len(rows)} of {agreed_sub_games} windows; the "
            "sibling process's half was not available at filing time — its "
            "rows appear in no document unless it files separately"
        )
    started = [str(game.get("started_at", "")) for game in games if game.get("started_at")]
    ended = [str(game.get("ended_at", "")) for game in games if game.get("ended_at")]
    if started:
        extra["game_started_at"] = min(started)
    if ended:
        extra["game_ended_at"] = max(ended)
    return extra
