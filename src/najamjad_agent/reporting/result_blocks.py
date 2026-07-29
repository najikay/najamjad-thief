"""What the result report *says* — the blocks, separate from the filing of them.

Split out of `filing` when that module crossed the size cap holding two jobs:
deciding the content of each block, and orchestrating when files get written
and mailed. They change for different reasons — a schema drift against the
lecturer's sample versus a change in when we file — and reviewing them apart is
what makes a drift visible.
"""

from __future__ import annotations

from typing import Any

from ..protocol.schemas_report import log_filename
from ..shared.sysinfo import git_commit


def sub_game_rows(
    games: list[dict[str, Any]],
    outcomes: list[Any],
    groups: tuple[str, str],
    game_id: str,
) -> list[dict[str, Any]]:
    """One row per mini-game, in the shape the result artifact declares.

    `log_files` names both peers' copies of the same mini-game. The lecturer's
    own sample carries it, so a reader can find the two logs whose commits must
    agree; omitting it costs nothing at parse time and everything at review.
    """
    ours, theirs = groups
    commit = git_commit()
    rows = []
    for game, outcome in zip(games, outcomes, strict=False):
        number = int(game.get("sub_game", 0))
        role = str(game.get("role", ""))
        verified = game.get("audit") == "Verified OK"
        rows.append({
            "sub_game_number": number,
            "roles": {ours: role, theirs: _opposite(role)},
            "result": str(game.get("end_reason", "")),
            "winner_group": _winner(outcome, groups),
            "tie": outcome.our_score == outcome.their_score,
            "score": {ours: outcome.our_score, theirs: outcome.their_score},
            "tokens": {ours: int(game.get("tokens", 0)), theirs: 0},
            "github_commit": {ours: commit, theirs: str(game.get("their_commit", "unknown"))},
            "started_at": str(game.get("started_at", "")),
            "ended_at": str(game.get("ended_at", "")),
            "audit": {"log_verified": verified, "tampered": game.get("audit") == "TAMPERED"},
            "log_files": {
                ours: f"{ours}/{log_filename(game_id, number)}",
                theirs: f"{theirs}/{log_filename(game_id, number)}",
            },
        })
    return rows


def winning_role(row: dict[str, Any], ours: str) -> str:
    """Which seat won this mini-game, or empty on a tie."""
    winner = row["winner_group"]
    if winner is None:
        return ""
    return row["roles"][winner] if winner in row["roles"] else row["roles"][ours]


def _opposite(role: str) -> str:
    """The role the opponent held while we held this one."""
    return "thief" if role == "police" else "police"


def _winner(outcome: Any, groups: tuple[str, str]) -> str | None:
    """Which group took this mini-game, or None on a tie."""
    ours, theirs = groups
    if outcome.our_score > outcome.their_score:
        return ours
    if outcome.their_score > outcome.our_score:
        return theirs
    return None


def series_tokens(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Per-group token totals across the series, summed from the sub-game rows.

    `final_result_block` has always accepted a `tokens` argument and nothing
    ever passed one, so `tokens_total_series` shipped as `{}` while the
    lecturer's own sample carries an entry per group. A league table reading
    our file found the key present and empty, which is not the same as zero.

    Summed from the rows rather than read off a meter so the series total and
    the per-game numbers cannot disagree — they are the same numbers by
    construction.
    """
    totals: dict[str, int] = {}
    for row in rows:
        for group, spent in dict(row.get("tokens") or {}).items():
            totals[group] = totals.get(group, 0) + int(spent)
    return totals


def final_result_block(
    result: Any, tokens: dict[str, int] | None = None, rename: dict[str, str] | None = None
) -> dict[str, Any]:
    """Series totals, as the league table reads them.

    `rename` maps the tracker's placeholder for the opponent onto the group id
    the handshake actually learned. The tracker is built before we have spoken
    to anyone, so it scores against `"them"`; leaving that in the file would put
    one name in `groups` and a different one in `total_score`, and a league
    table keyed by group id would silently miss the match.
    """
    swap = rename or {}
    relabel = lambda block: {swap.get(k, k): v for k, v in dict(block).items()}  # noqa: E731
    return {
        "total_score": relabel(result.total_score),
        "sub_games_won": relabel(result.sub_games_won),
        "ties": int(result.ties),
        "winner_group": result.winner_group,
        "series_tie": bool(result.series_tie),
        "tokens_total_series": dict(tokens or {}),
    }


