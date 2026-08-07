"""Reading the opponent's step-0 declaration out of the records they revealed.

Two fields of the result artifact belong to the other team and cannot be
computed from anything on our side: the git commit they played with (rules 49
and 53) and what the match cost them in tokens (rule 54). Both live in their
step-0 declaration, which arrives with the rest of their sealed records at the
audit and is already carried on every played record as `their_records`.

Until now neither was read. `github_commit` fell back to a `their_commit` key
that nothing in the project ever set, and the token figure was the literal `0`
— not a lookup that failed but a constant, so it would have stayed 0 against a
peer who declared honestly.

**Token totals are running, not per-game.** A declaration states the series
spend *before* its own mini-game, so a game's cost is the difference between
consecutive declarations. Reading the field directly would report game four's
opening balance as its price and make the series total a sum of prefixes. The
last mini-game has no successor to subtract from and is therefore reported as
0: understating one game is a smaller lie than inventing it, and no declaration
that exists states the number.

Everything here degrades to "absent" rather than raising. This is a claim made
by the other team about themselves, arriving in a shape we do not control, and
a peer who declares nothing — most of them, today — must still produce a
filable report.
"""

from __future__ import annotations

from typing import Any

from .step_zero import RECORD_TYPE

UNKNOWN_COMMIT = "unknown"


def peer_facts(games: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Per mini-game, what the opponent declared about themselves.

    Keyed by sub-game number so the caller cannot mis-zip two lists; the games
    it is built from and the rows it is read into are ordered independently.
    """
    declared = {
        int(game.get("sub_game", 0)): _declaration(game.get("their_records")) for game in games
    }
    order = sorted(declared)
    facts: dict[int, dict[str, Any]] = {}
    for index, number in enumerate(order):
        payload = declared[number]
        following = declared[order[index + 1]] if index + 1 < len(order) else None
        facts[number] = {
            "commit": str(payload.get("github_commit") or UNKNOWN_COMMIT),
            "tokens": _spend_between(payload, following),
        }
    return facts


def _declaration(records: Any) -> dict[str, Any]:
    """Their step-0 payload from one mini-game's revealed records, or empty.

    Matched on `type` rather than on position or step number: the record is
    only meaningful if it says what it is, and a peer who orders their reveal
    differently is not thereby lying about their hardware.
    """
    for record in records or []:
        payload = record.get("payload") if isinstance(record, dict) else None
        if isinstance(payload, dict) and payload.get("type") == RECORD_TYPE:
            return payload
    return {}


def _spend_between(payload: dict[str, Any], following: dict[str, Any] | None) -> int:
    """One mini-game's token cost, as the gap between two running totals.

    Clamped at zero. A meter that appears to run backwards means the peer reset
    it between mini-games, and a negative cost subtracted from the series total
    would be worse than the missing figure it replaces.
    """
    if not payload or not following:
        return 0
    try:
        return max(int(following.get("tokens_total", 0)) - int(payload.get("tokens_total", 0)), 0)
    except (TypeError, ValueError):
        return 0
