"""What one mini-game leaves behind — the record every report is built from.

Split from `domain/match.py` when the handshake-retry fix (T-2447) pushed that
file past its line budget; splitting beats compressing. Coherent on its own:
the runner decides *when* a mini-game happened, this module decides what is
remembered about it, and the filer downstream reads exactly these keys.

Both shapes live here together so they cannot drift apart: a report builder
that finds `tokens` on a played game and a KeyError on an unplayed one would
fail at filing time — which rule 35 scores as not having played at all.
"""

from datetime import UTC, datetime
from typing import Any

from .audit import AuditReport
from .game_state import GameState
from .series import SubGameOutcome


def now_iso() -> str:
    """An aware UTC timestamp for the artifacts.

    Aware, not naive: a bare local time in a report read in another timezone
    is a different moment, and the lecturer's sample carries an offset.
    """
    return datetime.now(tz=UTC).isoformat()


def played_record(
    sub_game: int,
    started_at: str,
    outcome: SubGameOutcome,
    state: GameState,
    report: AuditReport,
    tokens: int,
) -> dict[str, Any]:
    """A finished mini-game, in the shape the filer and dashboard read.

    `records` only after an audit actually happened: with no audit the nonces
    were never released, and the ledger rightly refuses to hand them over
    (rule 18) — a game that ended in a timeout has nothing to reveal.
    """
    return {
        "sub_game": sub_game,
        "started_at": started_at,
        "ended_at": now_iso(),
        "role": state.role.value,
        "end_reason": outcome.end_reason.value,
        "steps": state.step,
        "audit": report.banner,
        "records": [] if report.skipped else state.ledger.audit_payload(),
        "tokens": tokens,
        # Their stated outcome, and whether it contradicts ours — carried into
        # the report so `mutual_agreement` cannot claim we agreed with an
        # opponent who said something different (rules 33-35).
        "their_claim": report.their_claim,
        "their_records": list(report.their_records),
        "disputed": report.disputed,
    }


def unplayed_record(sub_game: int, started_at: str, outcome: SubGameOutcome) -> dict[str, Any]:
    """A mini-game that never started: the handshake died after bounded retries.

    Same keys as a played record, deliberately — one shape downstream, no
    special cases in the filer. There was no game, so there are no steps, no
    sealed records, no tokens, and nothing the opponent claimed: `disputed` is
    False because a peer that never agreed to play has not contradicted us.
    """
    return {
        "sub_game": sub_game,
        "started_at": started_at,
        "ended_at": now_iso(),
        "role": outcome.role.value,
        "end_reason": outcome.end_reason.value,
        "steps": 0,
        "audit": "handshake failed — never played",
        "records": [],
        "tokens": 0,
        "their_claim": None,
        "their_records": [],
        "disputed": False,
    }


def abandoned_record(
    sub_game: int, started_at: str, outcome: SubGameOutcome, steps: int
) -> dict[str, Any]:
    """A mini-game that agreed, played, and then died mid-flight.

    Distinct from `unplayed_record`, and the distinction is a scoring one. A
    hung game used to be filed through the unplayed path with `steps: 0`, so
    our report said "handshake failed - never played" about games in which we
    had sent a dozen sealed turns. uoh-sqak caught it with their own logs:
    27 inbound turns in g01, 11 in g03, 11 in g05, each carrying our commit
    hashes.

    That mislabel is worse than embarrassing. Their ledger reads a mid-game
    silence as a technical loss, which is what the book says; ours claimed the
    game never happened. Rules 33-35 void *both* teams' reports when they
    contradict, so shipping this would have turned every hung game into a
    dispute that costs us more than the loss did.

    No `records`: the game never reached an audit, so the nonces were never
    released and rule 18 keeps them sealed. `disputed` is False because the
    opponent did not contradict us — we went quiet, which is our fault.
    """
    return {
        "sub_game": sub_game,
        "started_at": started_at,
        "ended_at": now_iso(),
        "role": outcome.role.value,
        "end_reason": outcome.end_reason.value,
        "steps": steps,
        "audit": "AUDIT SKIPPED",
        "records": [],
        "tokens": 0,
        "their_claim": "",
        "their_records": [],
        "disputed": False,
    }
