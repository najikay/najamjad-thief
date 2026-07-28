"""Past matches, read back from the artifacts they produced.

The dashboard's answer to "what happened, and can I prove it". Everything here
is derived from `result_<game_id>.json` — the file we emailed — so what the
operator sees is exactly what the lecturer received, rather than a second
account assembled from memory that could disagree with it.

**Summaries only, never records.** The logs contain revealed payloads and their
nonces, and although a finished game's records are no longer secret, putting
them behind a web route is how a live game's would eventually follow. The
replay viewer is the place that reads records, from a file, deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULT_GLOB = "result_*.json"


def _load(path: Path) -> dict[str, Any] | None:
    """One result artifact, or None if it is unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def summarise(result: dict[str, Any], source: Path) -> dict[str, Any]:
    """One match, as a row in the browser."""
    sub_games = result.get("sub_games") or []
    final = result.get("final_result") or {}
    audits = [game.get("audit", {}) for game in sub_games]
    return {
        "game_id": result.get("game_id", source.stem),
        "game_uid": result.get("game_uid", ""),
        "groups": result.get("groups", []),
        "num_sub_games": result.get("num_sub_games", len(sub_games)),
        "total_score": final.get("total_score", {}),
        "winner_group": final.get("winner_group"),
        "series_tie": bool(final.get("series_tie", False)),
        # Two separate facts, and the difference matters: a game nobody audited
        # is not a game that failed its audit, and collapsing them would let a
        # timeout read as an accusation.
        "verified": sum(1 for audit in audits if audit.get("log_verified")),
        "tampered": sum(1 for audit in audits if audit.get("tampered")),
        "reported": bool((result.get("mutual_agreement") or {}).get("confirmed")),
        "sub_games": [
            {
                "sub_game_number": game.get("sub_game_number"),
                "result": game.get("result"),
                "winner_group": game.get("winner_group"),
                "score": game.get("score", {}),
                "roles": game.get("roles", {}),
                "audit": game.get("audit", {}),
            }
            for game in sub_games
        ],
        "artifacts": sorted(
            str(sibling.name) for sibling in source.parent.glob("*.json")
        ),
        "path": str(source),
    }


def match_history(*roots: Path | str) -> list[dict[str, Any]]:
    """Every match we can find, newest first.

    Several roots because artifacts land in the live workspace during a match
    and are archived per opponent afterwards; the operator wants one list, not
    two places to look.
    """
    found: dict[str, dict[str, Any]] = {}
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        for path in sorted(base.rglob(RESULT_GLOB)):
            result = _load(path)
            if result is None:
                continue
            summary = summarise(result, path)
            # Keyed by game_uid so the same match found in two roots appears
            # once; the archived copy wins because it is the settled one.
            found[summary["game_uid"] or summary["game_id"]] = summary
    return sorted(found.values(), key=lambda row: row["game_id"], reverse=True)


def standings(history: list[dict[str, Any]], ours: str) -> dict[str, Any]:
    """Our league position as the artifacts describe it.

    Counts *distinct opponents* as well as matches, because the league rewards
    diversity and a fifth match against the same team is worth less than a
    first against a new one.
    """
    played = [row for row in history if ours in (row.get("total_score") or {})]
    opponents = {
        group for row in played for group in row.get("groups", []) if group != ours
    }
    return {
        "matches": len(played),
        "distinct_opponents": len(opponents),
        "opponents": sorted(opponents),
        "won": sum(1 for row in played if row.get("winner_group") == ours),
        "tied": sum(1 for row in played if row.get("series_tie")),
        "points": sum(int((row.get("total_score") or {}).get(ours, 0)) for row in played),
        "unreported": [row["game_id"] for row in played if not row["reported"]],
        "tampered": [row["game_id"] for row in played if row["tampered"]],
    }
