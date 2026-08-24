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

import os
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

#: How many times a mini-game that died mid-play is re-offered under the same
#: number before it is scored. Bounded, so a genuinely dead peer still ends the
#: series rather than looping; two survives a boundary transient.
#:
#: The bound is what makes ONE behaviour correct against BOTH kinds of peer, so
#: we stop re-tuning per opponent. A settlement-gated peer is still holding the
#: window, so we match it on the first re-offer; a peer that also advances on
#: abandon has moved on, so we exhaust the bound, record and advance too —
#: converging rather than deadlocking. Unbounded would only suit the first kind.
#: Overridable per run: a peer whose relay collapses in bursts (bestteam's
#: ngrok dropped both doors at the 3-4 window mark, three runs straight) needs
#: more fresh attempts per window than the default's two — each attempt is
#: bounded by the gatekeeper's own budget, so extra ones cost minutes, not
#: hours. Default unchanged for everyone else.
ABANDON_RETRIES = int(os.environ.get("NAJAMJAD_ABANDON_RETRIES", "2"))
#: The same rule for a handshake that never agreed. Three, because each attempt
#: already spans a generous wait, so this is measured in whole windows.
HANDSHAKE_REOFFERS = 3


def retry_or_resolve(tracker: Any, attempts: dict[int, int], sub_game: int,
                     role: Role, steps: int, fault: dict[str, Any] | None,
                     emit: Any) -> dict[str, Any] | None:
    """Re-offer the window, or score it once the retries are spent.

    Returns the record to file, or None while we are still re-offering.

    `advance_to_ours` only READS the next number; `tracker.record`, inside
    `resolve_abandoned`, is what consumes it. So declining to record keeps us on
    this sub-game, and that is the whole mechanism.

    We used to record immediately, advancing past a window that never played.
    Against a settlement-gated peer that is unrecoverable: ours abandoned 3 and
    went to 5 while anrbj666 held 3 open, and every window either side offered
    was then refused by the other's guard — "sub_game_number: mine=3 theirs=5"
    in their own log. A skipped window cannot be filed anyway, so advancing past
    it costs the artifact too.
    """
    attempts[sub_game] = attempts.get(sub_game, 0) + 1
    if attempts[sub_game] < ABANDON_RETRIES:
        emit({"event": "subgame.retrying", "sub_game": sub_game,
              "attempt": attempts[sub_game], "of": ABANDON_RETRIES})
        return None
    return resolve_abandoned(tracker, sub_game, role, steps, fault)

def reoffer_or_quit(tracker: Any, attempts: dict[int, int], sub_game: int,
                    role: Role, emit: Any) -> dict[str, Any] | None:
    """Re-offer a window whose handshake never agreed, or finally score it.

    Returns the record to file, or None while the window is being re-offered.

    The abandon path stopped consuming unplayed numbers; this is the same rule
    for the other door. anrbj666's sequencing contract — windows run 1..6 and
    N+1 is not spawned until N settles — means a handshake that cannot agree is
    usually a window that has not started on their side yet, not one that never
    will. Scoring it `OPPONENT_QUIT` and advancing put our thief on 5 while they
    held 3, and every window either side offered was then refused by the other.

    Counted in the same dict as the abandon retries, deliberately: a window gets
    a fixed number of chances in total, however it failed, so a peer that is
    genuinely gone still ends the series.
    """
    attempts[sub_game] = attempts.get(sub_game, 0) + 1
    if attempts[sub_game] < HANDSHAKE_REOFFERS:
        emit({"event": "subgame.reoffering", "sub_game": sub_game,
              "attempt": attempts[sub_game], "of": HANDSHAKE_REOFFERS})
        return None
    return resolve_unplayed(tracker, sub_game, role, EndReason.OPPONENT_QUIT)
