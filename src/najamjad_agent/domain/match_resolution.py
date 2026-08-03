"""Scoring a mini-game that never produced a played result.

Two things can go wrong before a mini-game yields an outcome, and they are not
the same thing:

* the handshake never completed — the peer has nothing to reveal, so the game
  is genuinely unplayed;
* the handshake completed, turns were exchanged, and then it died — most often
  the `RuntimeError` the gatekeeper raises once a send has exhausted its
  retries.

Filing the second as the first is what cost us a scoring dispute against
uoh-sqak: our report said "handshake failed — never played" about mini-games in
which we had sent 11 to 27 sealed turns, and they had our turns in their logs.
Book rules 33-35 void *both* teams' reports when they contradict, so the lie was
more expensive than the loss. Both paths now go through here, side by side,
where the difference between them is one line and impossible to miss.
"""

from __future__ import annotations

from typing import Any

from ..constants import EndReason, Role
from .match_record import abandoned_record, now_iso, unplayed_record


def resolve_abandoned(
    tracker: Any, sub_game: int, role: Role, steps: int, fault: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Score a mini-game that played and then died — as played, not void.

    Input: the series tracker, the mini-game number, our role, steps reached.
    Output: the record to file for it.
    Setup: none.

    Scored `TIMEOUT`, which is the verdict the opponent's watchdog reaches when
    we go silent, so both ledgers describe the same event.
    """
    outcome = tracker.record(
        end_reason=EndReason.TIMEOUT, role=role, steps=steps, audit_passed=True
    )
    return {**abandoned_record(sub_game, now_iso(), outcome, steps), **(fault or {})}


def resolve_unplayed(tracker: Any, sub_game: int, role: Role, reason: EndReason) -> dict[str, Any]:
    """Score a mini-game that produced no result, and keep the series alive.

    Input: the series tracker, the mini-game number, our role, the end reason.
    Output: the record to file for it.
    Setup: none.

    `OPPONENT_QUIT` when the handshake never completed: a peer that never agreed
    has nothing to reveal, and demanding an audit would read absence as forgery.
    """
    outcome = tracker.record(end_reason=reason, role=role, steps=0, audit_passed=True)
    return unplayed_record(sub_game, now_iso(), outcome)


def tokens_for(meter: Any, sub_game: int) -> int:
    """Tokens spent on one mini-game, or 0 when nothing is metering.

    Read off the meter rather than counted at the call site: the meter is what
    the router already writes to and what the budget panel reads, so the report
    cannot disagree with the dashboard about how close to the cap we are.
    """
    if meter is None:
        return 0
    return int(getattr(meter, "per_sub_game", {}).get(sub_game, 0))
