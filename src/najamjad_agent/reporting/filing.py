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

from ..protocol.schemas_report import log_filename
from ..shared.events import Emit
from ..shared.sysinfo import git_commit
from .artifacts import ArtifactWriter


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
            "tie": outcome.our_score == outcome.their_score,
            "score": {ours: outcome.our_score, theirs: outcome.their_score},
            "tokens": {ours: int(game.get("tokens", 0)), theirs: 0},
            "github_commit": {ours: commit, theirs: str(game.get("their_commit", "unknown"))},
            "started_at": str(game.get("started_at", "")),
            "ended_at": str(game.get("ended_at", "")),
            "audit": {"log_verified": verified, "tampered": game.get("audit") == "TAMPERED"},
            "log_files": {
                ours: f"{ours}/{log_filename(game_id, number)}",
                theirs: f"{theirs}/{log_filename(game_id, number)}",
            },
        })
    return rows


def _winning_role(row: dict[str, Any], ours: str) -> str:
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
        "winner_group": result.winner_group,
        "series_tie": bool(result.series_tie),
        "tokens_total_series": dict(tokens or {}),
    }


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
            rows, final_result_block(result, rename=self.rename), theirs, confirmed
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
            "winner_role": _winning_role(row, ours),
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



