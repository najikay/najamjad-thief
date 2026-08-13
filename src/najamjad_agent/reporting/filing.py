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

from ..constants import is_technical
from ..shared.events import Emit
from ..shared.practice import current
from .artifacts import ArtifactWriter
from .league import league_block
from .mail_message import report_subject
from .reconcile import MISMATCH, from_recorded_games
from .resilient_filing import attempt, missing
from .result_blocks import (
    final_result_block,
    repository_links,
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
        confirmed: bool | None = None,
        emission: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Write all four artifacts and return where they went.

        `confirmed` defaulted to `True` and no caller ever passed it, so every
        report we have filed asserted mutual agreement with the opponent
        without checking anything. Under rules 33-35 both sides must agree and
        contradictory reports void both, so that is a claim worth earning.

        Left unset, it is now *derived* from the audits: agreement means every
        mini-game's sealed log was verified and none was tampered — which is
        mutual verification we actually performed, on evidence the opponent
        revealed. It is narrower than comparing final results (that needs a
        result exchange, T-1725) and it is true.
        """
        _, theirs = self._groups
        rows = sub_game_rows(games, outcomes, self._groups, self._game_id)
        if confirmed is None:
            # Agreement means two things, and only the first was ever checked:
            # every sealed log verified, AND neither side stated an outcome the
            # other contradicted. A dispute is precisely what rules 33-35 void
            # both teams for, so reporting one as agreement is the worst
            # available answer.
            #
            # **A skipped audit is not a failed one**, and treating it as one
            # was costing us the flag on whole series. A technical ending has no
            # reveal to verify — nobody refused, there is simply nothing there —
            # so `log_verified` is false and one timeout in six games flipped
            # the entire series to `confirmed: false`. An opponent whose rule is
            # "no contradiction means agreed" files `true`, and two reports
            # disagreeing about agreement is itself the contradiction rules
            # 33-35 void both teams for. This is the same distinction
            # `MatchRunner` already draws when it scores a game.
            # `reconcile` has existed since early on, fully tested, with no
            # production caller — component #12 of that family, and the one
            # whose absence meant `mutual_agreement.confirmed` was never an
            # agreement *with the opponent* at all, only a statement about our
            # own audits. It is now the authority on the dispute half.
            settlement = from_recorded_games(
                self._game_id, self._writer.game_uid, self._groups, rows, games
            )
            alert = settlement.operator_alert()
            if alert is not None:
                self._emit(alert)
            tampered = any(row["audit"]["tampered"] for row in rows)
            unverified = any(
                not row["audit"]["log_verified"] and not is_technical(row["result"])
                for row in rows
            )
            # Both halves must hold: our own evidence has to be sound *and*
            # the opponent must not have contradicted us.
            confirmed = not tampered and not unverified and settlement.status != MISMATCH
        written: dict[str, Any] = {"config": [], "log": []}

        # Every write is attempted independently. One mini-game's log failing
        # must never suppress the `result` artifact below it — that is the file
        # the league grades, and losing it scores as not having played (rule 35).
        # `emission` says what we chose to transmit this match. Emitting less
        # than the maximum is a tactical choice and not a secret one: rule 49
        # means the lecturer reads these repositories, and a documented setting
        # reads as the choice it is where the same behaviour undeclared reads as
        # something we were hiding. It rides in the artifact rather than the
        # handshake identity on purpose — a peer's strict declaration model once
        # rejected a whole block over an unexpected key, costing six played
        # games their artifacts, and we will not hand anyone that.
        extra: dict[str, Any] = {"emission": emission} if emission else {}
        # The declaration used to ship the schema defaults — 6 sub-games and the
        # default token cap — while the result beside it computed `num_sub_games`
        # from the games actually played. A two-game match therefore filed a
        # declaration saying six, so our own artifact set contradicted itself in
        # front of a grader. Both now come from the same match.
        extra["num_sub_games"] = len(rows) or 1
        # Empty strings in the golden's place. They are ours to fill: the first
        # game's start and the last game's end are both on the records.
        started = [str(game.get("started_at", "")) for game in games if game.get("started_at")]
        ended = [str(game.get("ended_at", "")) for game in games if game.get("ended_at")]
        if started:
            extra["game_started_at"] = min(started)
        if ended:
            extra["game_ended_at"] = max(ended)
        written["declaration"] = attempt(
            "declaration",
            lambda: self._writer.write_declaration(groups_block, **extra),
            self._emit,
        )
        for game, row in zip(games, rows, strict=False):
            number = int(game.get("sub_game", 0))
            written["config"].append(attempt(
                f"config/g{number:02d}",
                lambda n=number: self._writer.write_config(n, terms, config_sha256),
                self._emit,
            ))
            written["log"].append(attempt(
                f"log/g{number:02d}",
                lambda g=game, r=row, n=number: self._writer.write_log(
                    n, self._log_summary(g, r), list(g.get("records") or []),
                    theirs, confirmed, rows,
                    opponent_records=list(g.get("their_records") or []),
                ),
                self._emit,
            ))
        written["result"] = attempt(
            "result",
            lambda: self._writer.write_result(
                rows,
                # The league fields are outside every hash, but rule 38 judges
                # counted-match declarations on consistency between the two
                # teams' files, so a missing count is not cosmetic. Computed
                # here, inside `attempt`, because it reads `result` — which a
                # caller may not have, and one block failing must never take the
                # rest of the filing with it.
                final_result_block(result, series_tokens(rows), self.rename, league_block(
                    groups_block or {}, not current().enabled, self._groups,
                    result=result, rename=self.rename)),
                theirs,
                confirmed,
                repositories=repository_links(groups_block or {}),
            ),
            self._emit,
        )
        self._emit({"event": "artifacts.written", **{k: len(v) if isinstance(v, list) else 1
                                                     for k, v in written.items()}})
        gaps = missing(written)
        if gaps:
            self._emit({"event": "artifacts.incomplete", "missing": gaps})
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
                # The audit's count, not the game's length. These were the
                # step count and an empty list, so a failed audit named no step.
                "verified_steps": len(list(game.get("verified_steps") or [])),
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
        # Body = the attachment's exact bytes, not a re-serialization of the
        # same object. Graders compare emails, and a body derived from parsed
        # content can differ from the attachment while every hash still agrees —
        # two teams looking identical by digest and different on screen. The
        # subject is the reference's verbatim form, which names the winner; ours
        # named only the game. Both are outside every hash and refuse nothing.
        report = Path(result_path)
        sent = self._sender.send_report(
            report,
            subject=report_subject(report, self._groups[0], self._game_id),
            body=report.read_text(encoding="utf-8"),
        )
        #: Kept so the caller can hand it to the dashboard's report panel,
        #: which needs the delivery object rather than just the id.
        self.last_send = sent
        self._emit(
            {
                "event": "report.sent",
                "message_id": sent.message_id,
                "recipient": sent.recipient,
                "mode": sent.mode,
            }
        )
        return sent.message_id



