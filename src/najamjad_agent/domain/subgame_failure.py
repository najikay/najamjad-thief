"""The record a mini-game leaves when we could not finish it.

Split from `match` to stay inside the file budget. It exists because a
mini-game that blows up must cost *that* mini-game and nothing more: in a real
match three failed `receive_turn` calls at sub-game 3 killed the process, so
sub-games 4, 5 and 6 were never played. The opponent scored the blip with a
watchdog and carried on; we forfeited four games to one bad moment on the wire.

Scored as a `TIMEOUT`, which is what an opponent's watchdog calls it — so both
sides reach the same verdict about a game one of us never finished, rather than
filing contradictory reports (rules 33-35).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def abandoned_record(sub_game: int, role: str, tokens: int = 0) -> dict[str, Any]:
    """The artifact row for a mini-game we could not complete.

    Input: which mini-game, the role we were playing, tokens spent before it
        failed.
    Output: a record shaped like a played one, so the filer needs no special
        case and the report still accounts for every mini-game.
    Setup: none.

    `records` is empty and the audit reads `AUDIT SKIPPED`, not `TAMPERED`: we
    revealed nothing because there was nothing to reveal, and accusing an
    opponent of forgery for our own dropped connection would be a false report.
    """
    return {
        "sub_game": sub_game,
        "role": role,
        "end_reason": "timeout",
        "steps": 0,
        "audit": "AUDIT SKIPPED",
        "records": [],
        "tokens": tokens,
        "started_at": "",
        "ended_at": datetime.now(tz=UTC).isoformat(),
        "their_claim": "",
        "disputed": False,
        "their_records": [],
    }
