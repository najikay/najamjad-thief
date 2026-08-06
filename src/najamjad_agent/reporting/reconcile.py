"""Agreeing the result with the opponent *before* anybody emails the lecturer.

Rule 35 is the harshest in the book: contradictory reports void the match for
**both** teams. So the expensive failure is not disagreeing — it is disagreeing
silently and both sides discovering it at grading.

This module compares our symmetric outcome with theirs, and its verdict is what
sets `mutual_agreement.confirmed`. That is the whole fix for Assignment 6's
`agreement: null`: the flag is not a default we hope is right, it is the
recorded outcome of an exchange that actually happened.

A mismatch does not silently pick a winner. It holds the send and hands the
operator both versions side by side, because a wrong-but-confident report is
worse than a late one.
"""

from dataclasses import dataclass, field
from typing import Any

from .agreement import agreement_hash, symmetric_outcome

AGREED = "agreed"
MISMATCH = "mismatch"
NO_REPLY = "no_reply"


@dataclass
class Reconciliation:
    """The outcome of comparing our result with the opponent's."""

    status: str
    ours: dict[str, Any] = field(default_factory=dict)
    theirs: dict[str, Any] = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        """The boolean that goes into `mutual_agreement.confirmed`."""
        return self.status == AGREED

    @property
    def may_send(self) -> bool:
        """Whether the report may go out without an operator decision.

        A missing reply still permits sending: rule 35 also punishes *not*
        reporting, so silence from the opponent must not stop us filing.
        """
        return self.status in (AGREED, NO_REPLY)

    def operator_alert(self) -> dict[str, Any] | None:
        """Both versions side by side, when a human needs to look."""
        if self.status != MISMATCH:
            return None
        return {
            "event": "result.mismatch",
            "differences": self.differences,
            "ours": self.ours,
            "theirs": self.theirs,
        }


def _describe(path: str, ours: Any, theirs: Any) -> str:
    return f"{path}: ours={ours!r} theirs={theirs!r}"


def _diff(ours: Any, theirs: Any, path: str = "") -> list[str]:
    """Human-readable differences between two symmetric outcomes."""
    if isinstance(ours, dict) and isinstance(theirs, dict):
        differences: list[str] = []
        for key in sorted(set(ours) | set(theirs)):
            child = f"{path}.{key}" if path else str(key)
            if key not in ours:
                differences.append(f"{child}: missing on our side")
            elif key not in theirs:
                differences.append(f"{child}: missing on their side")
            else:
                differences.extend(_diff(ours[key], theirs[key], child))
        return differences
    if isinstance(ours, list) and isinstance(theirs, list):
        if len(ours) != len(theirs):
            return [_describe(f"{path}.length", len(ours), len(theirs))]
        return [
            difference
            for index, (mine, yours) in enumerate(zip(ours, theirs, strict=True))
            for difference in _diff(mine, yours, f"{path}[{index}]")
        ]
    return [] if ours == theirs else [_describe(path or "<root>", ours, theirs)]


def reconcile(
    game_id: str,
    game_uid: str,
    groups: tuple[str, str],
    our_sub_games: list[dict[str, Any]],
    their_summary: dict[str, Any] | None,
) -> Reconciliation:
    """Compare our result with the opponent's before either of us reports."""
    ours = symmetric_outcome(game_id, game_uid, groups, our_sub_games)
    if not their_summary:
        return Reconciliation(status=NO_REPLY, ours=ours)

    theirs = their_summary.get("outcome") or their_summary
    their_hash = str(their_summary.get("sha256", ""))
    our_hash = agreement_hash(game_id, game_uid, groups, our_sub_games)

    # A hash is only evidence if it describes the data sent with it. A stale
    # hash beside fresh rows means their reporting is inconsistent, and calling
    # that "agreement" is how both teams end up with a voided match.
    if their_hash and their_hash == our_hash and theirs == ours:
        return Reconciliation(status=AGREED, ours=ours, theirs=theirs)
    if their_hash and their_hash == our_hash and theirs != ours:
        return Reconciliation(
            status=MISMATCH,
            ours=ours,
            theirs=theirs,
            differences=["their signature matches ours but their outcome data does not"]
            + _diff(ours, theirs),
        )

    differences = _diff(ours, theirs) or ["signature differs but no field-level difference found"]
    return Reconciliation(status=MISMATCH, ours=ours, theirs=theirs, differences=differences)


def our_summary(
    game_id: str, game_uid: str, groups: tuple[str, str], sub_games: list[dict[str, Any]]
) -> dict[str, Any]:
    """What we send the opponent so they can run the same comparison."""
    return {
        "sha256": agreement_hash(game_id, game_uid, groups, sub_games),
        "outcome": symmetric_outcome(game_id, game_uid, groups, sub_games),
    }


def from_recorded_games(
    game_id: str,
    game_uid: str,
    groups: tuple[str, str],
    our_sub_games: list[dict[str, Any]],
    games: list[dict[str, Any]],
) -> Reconciliation:
    """Reconcile from what the opponent told us *during* the match.

    Input: the identifiers, our symmetric rows, and the raw per-mini-game
    records.
    Output: a `Reconciliation` whose status is real rather than assumed.
    Setup: none, and no network — every input is already on disk.

    **Why not exchange summaries on the wire.** `reconcile` was written for a
    result exchange that does not exist, and inventing one now would be a poor
    trade: `ControlMessage` validates `kind` against a closed set and *rejects*
    anything else, so a new verb would be refused by every conforming peer and
    look like a protocol violation days before four counted matches.

    We do not need it. Rules 18-22 already make the opponent state each
    mini-game's ending, `match_audit` records it as `their_claim`, and the
    orchestrator sets `disputed` when their claim contradicts ours. That is the
    contradiction rules 33-35 void a match for — recorded, per game, from
    evidence they revealed. This assembles it into the verdict the module was
    always meant to produce.

    Three outcomes, and the middle one is the point. A peer that claimed
    endings and never contradicted us is `AGREED`; one that contradicted us is
    `MISMATCH`, which holds the send and hands the operator both versions; one
    that told us nothing — every game technical, say — is `NO_REPLY`, which
    still permits filing, because rule 35 punishes not reporting too.
    """
    ours = symmetric_outcome(game_id, game_uid, groups, our_sub_games)
    disputes = [
        _describe(f"sub_game[{game.get('sub_game')}]", game.get("end_reason"), game.get("their_claim"))
        for game in games
        if game.get("disputed")
    ]
    if disputes:
        return Reconciliation(status=MISMATCH, ours=ours, differences=disputes)
    if not any(str(game.get("their_claim") or "").strip() for game in games):
        return Reconciliation(status=NO_REPLY, ours=ours)
    return Reconciliation(status=AGREED, ours=ours, theirs=ours)
