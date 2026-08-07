"""The mutual-agreement hash — the field that must match on both machines.

Rule 35 voids a match for **both** teams when their reports contradict each
other, so the one thing our report and the opponent's must agree on byte-for-byte
is this signature. That constrains what may go into it: only facts both peers
observe identically.

Per-peer facts are therefore excluded on purpose — our role in a mini-game, our
token spend, our commit hash, the order we happen to list ourselves in. Hashing
any of those would guarantee two different signatures and void the match we just
won. Group ids are sorted, and scores are keyed by group rather than by "us" and
"them", so the same dictionary is produced on both sides.
"""

import hashlib
from typing import Any

from ..protocol.canonical import canonical_json


def symmetric_outcome(
    game_id: str,
    game_uid: str,
    groups: tuple[str, str],
    sub_games: list[dict[str, Any]],
) -> dict[str, Any]:
    """The subset of the result both peers compute identically."""
    ordered = sorted(groups)
    rows = []
    for row in sub_games:
        scores = row.get("score", {}) or {}
        roles = row.get("roles", {}) or {}
        rows.append(
            {
                "sub_game_number": int(row.get("sub_game_number", 0)),
                "result": str(row.get("result", "")),
                "winner_group": row.get("winner_group"),
                # Keyed by group id, so both peers build the identical mapping —
                # which is what makes a per-peer fact safe to hash. The reference
                # includes roles in its preimage and we did not, so our digest
                # differed from a reference-derived opponent's for the same
                # series. Under rule 35 a differing sha256 is indistinguishable
                # from contradictory reports, and being *more* cautious than the
                # reference cuts the wrong way here: the safety we gained by
                # omitting a symmetric field cost us agreement with the peers we
                # most need to agree with.
                "roles": {group: str(roles.get(group, "")) for group in ordered},
                "score": {group: int(scores.get(group, 0)) for group in ordered},
            }
        )
    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "groups": ordered,
        "sub_games": sorted(rows, key=lambda row: row["sub_game_number"]),
    }


def agreement_hash(
    game_id: str,
    game_uid: str,
    groups: tuple[str, str],
    sub_games: list[dict[str, Any]],
) -> str:
    """SHA-256 over the symmetric outcome — identical on both peers."""
    payload = symmetric_outcome(game_id, game_uid, groups, sub_games)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def agreement_block(
    game_id: str,
    game_uid: str,
    groups: tuple[str, str],
    sub_games: list[dict[str, Any]],
    opponent_group_id: str,
    confirmed: bool,
) -> dict[str, Any]:
    """The `mutual_agreement` block for the log and result artifacts.

    `confirmed` must be a real boolean produced by the reconciliation step.
    A None is refused rather than coerced: `bool(None)` would quietly write
    "not agreed" for a match we simply forgot to reconcile, which is Assignment
    6's failure wearing a different mask — a plausible-looking report that
    misstates what happened.
    """
    if not isinstance(confirmed, bool):
        raise TypeError(
            f"mutual_agreement.confirmed must be a bool from reconciliation; "
            f"got {type(confirmed).__name__}"
        )
    return {
        "sha256": agreement_hash(game_id, game_uid, groups, sub_games),
        "confirmed": confirmed,
        "opponent_group_id": opponent_group_id,
    }
