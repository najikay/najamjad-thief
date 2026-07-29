"""Turning a finished match into the four artifacts and the emailed result.

Everything below already existed and was unit-tested; none of it was ever
*called*. A full six-game match against the reference produced zero artifacts on
our side while the opponent wrote all four, because `ArtifactWriter` had no
caller outside the test suite. The machinery was built and never plugged in —
which is the same defect that lost Assignment 6 its report, one level up.

This module is the plug. It has no rules of its own: the runner decides how a
game ended, the tracker scores it, and this turns those into files whose shape
the grader and the opponent both expect.

Failure here must never look like success. If a file cannot be written or the
mail cannot go, the reason is recorded and raised — a match we cannot file is
worse than a match we lost, because rule 35 punishes not reporting as heavily as
reporting falsely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shared.events import Emit
from .artifacts import ArtifactWriter
from .result_blocks import (
    final_result_block,
    series_tokens,
    sub_game_rows,
    winning_role,
)

__all__ = ["MatchFiler", "final_result_block", "series_tokens", "sub_game_rows"]


class MatchFiler:
    """Writes a match's artifacts and sends the result."""

    def __init__(
        self,
        workspace: Path,
        game_id: str,
        game_uid: str,
        groups: tuple[str, str],
        sender: Any = None,
        emit: Emit | None = None,
        rename: dict[str, str] | None = None,
    ) -> None:
        """Bind to one match; `sender` may be None while testing offline."""
        self.rename = rename or {}
        self._writer = ArtifactWriter(workspace, game_id, game_uid, groups, alert=emit)
        self._groups = groups
        self._game_id = game_id
        self._sender = sender
        self._emit = emit or (lambda _event: None)

    def file_match(
        self,
        games: list[dict[str, Any]],
        outcomes: list[Any],
        result: Any,
        terms: dict[str, Any],
        config_sha256: str,
        groups_block: dict[str, Any],
        confirmed: bool = True,
    ) -> dict[str, Any]:
        """Write all four artifacts and return where they went."""
        _, theirs = self._groups
        rows = sub_game_rows(games, outcomes, self._groups, self._game_id)
        written: dict[str, Any] = {"config": [], "log": []}

        written["declaration"] = str(self._writer.write_declaration(groups_block))
        for game, row in zip(games, rows, strict=False):
            number = int(game.get("sub_game", 0))
            written["config"].append(
                str(self._writer.write_config(number, terms, config_sha256))
            )
            written["log"].append(str(self._writer.write_log(
                number, self._log_summary(game, row), list(game.get("records") or []),
                theirs, confirmed, rows,
            )))
        written["result"] = str(self._writer.write_result(
            rows,
            final_result_block(result, tokens=series_tokens(rows), rename=self.rename),
            theirs,
            confirmed,
        ))
        self._emit({"event": "artifacts.written", **{k: len(v) if isinstance(v, list) else 1
                                                     for k, v in written.items()}})
        return written

    def _log_summary(self, game: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        """The header block of one mini-game log.

        `winner_role` rather than `winner_group`: a log describes one game from
        one seat, and the roles swap every mini-game — naming the group here
        would make the file ambiguous once read out of order.
        """
        ours, theirs = self._groups
        return {
            "sub_game_number": row["sub_game_number"],
            "group_id": ours,
            "role": str(game.get("role", "")),
            "opponent_group_id": theirs,
            "result": row["result"],
            "winner_role": winning_role(row, ours),
            "steps": int(game.get("steps", 0)),
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "tokens_total": int(game.get("tokens", 0)),
            "audit": {
                "passed": row["audit"]["log_verified"],
                "verified_steps": int(game.get("steps", 0)),
                "failed_steps": list(game.get("failed_steps") or []),
            },
        }

    def send(self, result_path: str | Path) -> str | None:
        """Email the result; returns the message id, or None when not wired.

        `send_report` returns a `SendResult`, not an id. This used to put the
        dataclass itself into the event, which is not JSON-serialisable, so the
        emit raised and the whole filing step was recorded as failed *after the
        mail had already gone out* — the worst possible reading of the state.

        It survived the life of the project because no Gmail service was ever
        injected: every send raised one line earlier, and this line had never
        run. A dead code path cannot be wrong, right up until it is reached.
        """
        if self._sender is None:
            self._emit({"event": "report.not_sent", "reason": "no mail sender configured"})
            return None
        sent = self._sender.send_report(Path(result_path), subject=self._game_id)
        self._emit(
            {
                "event": "report.sent",
                "message_id": sent.message_id,
                "recipient": sent.recipient,
                "mode": sent.mode,
            }
        )
        return sent.message_id



