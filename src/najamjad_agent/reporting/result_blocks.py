"""What the result report *says* — the blocks, separate from the filing of them.

Split out of `filing` when that module crossed the size cap holding two jobs:
deciding the content of each block, and orchestrating when files get written
and mailed. They change for different reasons — a schema drift against the
lecturer's sample versus a change in when we file — and reviewing them apart is
what makes a drift visible.
"""

from __future__ import annotations

from typing import Any

from ..constants import is_technical
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
            # Equal scores are how a tie is detected, and a technical ending
            # scores 0/0 for both — so every abandoned game used to be filed
            # as a draw. It is not one: nobody drew, the game never finished.
            "tie": outcome.our_score == outcome.their_score
            and not is_technical(game.get("end_reason")),
            "score": {ours: outcome.our_score, theirs: outcome.their_score},
            "tokens": {ours: int(game.get("tokens", 0)), theirs: 0},
            "github_commit": {ours: commit, theirs: str(game.get("their_commit", "unknown"))},
            "started_at": str(game.get("started_at", "")),
            "ended_at": str(game.get("ended_at", "")),
            "audit": {"log_verified": verified, "tampered": game.get("audit") == "TAMPERED"},
            # Bare filenames, as the golden writes them. The `<group>/` prefix
            # named twelve directories that do not exist — artifacts sit flat —
            # and contradicted `all_logs` in the same file, which lists the same
            # files unprefixed. `logs/<group_id>/` is where the reference *puts*
            # its logs on disk, not what it records here.
            "log_files": {
                ours: log_filename(game_id, number),
                theirs: log_filename(game_id, number),
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
        # Stated rather than folded into `ties`. A reader comparing our
        # report against the opponent's needs to see that three mini-games
        # ended off the board, not that three of them were drawn.
        "technical_endings": int(getattr(result, "technical", 0)),
        "winner_group": result.winner_group,
        "series_tie": bool(result.series_tie),
        "tokens_total_series": dict(tokens or {}),
        **({"tie_award": award} if result.series_tie and (award := getattr(
            result, "tie_award", None)) is not None else {}),
    }




#: Field names other teams use for the same hardware claim. The reference's
#: names are ours; these are what real opponents actually sent.
SPEC_ALIASES = {
    "cpu": "cpu_type",
    "processor": "cpu_type",
    "cpu_count": "cpu_cores",
    "cores": "cpu_cores",
    "ram": "ram_gb",
    "memory_gb": "ram_gb",
    "gpu": "gpu_model",
    "gpu_type": "gpu_model",
}


def normalise_spec(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Their hardware claim in our field names, or None if unusable.

    Returns None rather than raising: an opponent's declaration is *their*
    claim, and a shape we cannot read is a gap in the fairness data, never a
    reason to abandon a match we already played.
    """
    mapped = {SPEC_ALIASES.get(str(key), str(key)): value for key, value in (raw or {}).items()}
    try:
        return {
            **mapped,
            "cpu_type": str(mapped["cpu_type"]),
            "cpu_cores": int(mapped["cpu_cores"]),
            "ram_gb": float(mapped["ram_gb"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def declaration_group(identity: dict[str, Any]) -> dict[str, Any]:
    """One group's declaration block, translated from the wire identity.

    The wire calls the hardware block `spec`, because that is what the
    reference's declaration builder reads; our artifact schema calls it
    `hardware_spec`. Nothing mapped between the two, so every declaration we
    filed carried `hardware_spec: null` for both groups — the Step-0
    computational-fairness declaration (rule 24) with the hardware missing,
    while the identity beside it held the whole spec.

    Both names are kept on the way out: the artifact needs `hardware_spec`,
    and dropping `spec` would change what a reader of the raw identity sees.

    The opponent's block is normalised, never validated. `uoh-sqak` declared
    `cpu`/`cpu_count` where our schema wants `cpu_type`/`cpu_cores`, and the
    strict model rejected the entire declaration — six games played, zero
    artifacts written, nothing emailed, which rule 35 scores as not having
    played. Their names map to ours where we recognise them; where we do not,
    the hardware block is dropped and the raw claim kept under `spec`, so the
    cost of an unreadable spec is that one field and not the match.
    """
    block = dict(identity or {})
    spec = block.get("hardware_spec") or block.get("spec")
    if not spec:
        return block
    normalised = normalise_spec(spec)
    if normalised is None:
        block.pop("hardware_spec", None)
        return block
    block["hardware_spec"] = normalised
    return block


def repository_links(identities: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Both teams' repo links for the emailed result (rule 49, chapter 9.4).

    Taken from the identities exchanged at the handshake, so the opponent's
    links are the ones they declared rather than ones we guessed. A side that
    declared none is omitted entirely instead of appearing with empty strings,
    because an empty link reads as a broken repository rather than an absent
    declaration.
    """
    links: dict[str, dict[str, str]] = {}
    for group, identity in (identities or {}).items():
        repos = {str(k): str(v) for k, v in dict((identity or {}).get("repos") or {}).items() if v}
        if repos:
            links[str(group)] = repos
    return links
