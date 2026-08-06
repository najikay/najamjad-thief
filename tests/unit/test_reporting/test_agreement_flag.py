"""A skipped audit is not a failed one — and treating it as one voids matches.

`mutual_agreement.confirmed` is the field that says our report and the
opponent's do not contradict each other. It used to require *every* mini-game's
sealed log to be verified, and a technical ending has no reveal to verify —
nobody refused, there is simply nothing there. So one timeout in six games
flipped the whole series to `confirmed: false`, while an opponent whose rule is
"no contradiction means agreed" filed `true`.

Two reports disagreeing about whether they agree is itself the contradiction
rules 33-35 void both teams for. `MatchRunner` already draws this distinction
when it scores a game (`audit_passed=report.passed or report.skipped`); this is
the same rule applied to the report.
"""

import json
import pathlib

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.series import SeriesResult, SubGameOutcome
from najamjad_agent.reporting.filing import MatchFiler

GROUPS = ("najamjad", "rival")


def _game(number: int, reason: str, audit: str) -> dict:
    return {
        "sub_game": number,
        "role": "police" if number % 2 else "thief",
        "end_reason": reason,
        "audit": audit,
        "started_at": "2026-08-05T00:00:00Z",
        "steps": 12,
        "score": {"najamjad": 20, "rival": 5},
        "tokens": 0,
    }


def _outcome(number: int, reason: EndReason) -> SubGameOutcome:
    return SubGameOutcome(
        sub_game=number,
        role=Role.COP if number % 2 else Role.THIEF,
        end_reason=reason,
        our_score=20,
        their_score=5,
        steps=12,
    )


def _confirmed(tmp_path, games, outcomes) -> bool:
    filer = MatchFiler(tmp_path, "najamjad-vs-rival", "uid-1", GROUPS)
    result = SeriesResult(
        total_score={"najamjad": 20, "rival": 5},
        sub_games_won={"najamjad": 1, "rival": 0},
        ties=0,
        winner_group="najamjad",
        series_tie=False,
    )
    written = filer.file_match(games, outcomes, result, {}, "sha", {"najamjad": {}, "rival": {}})
    # `attempt()` returns the path as a string (or None on failure), not a Path.
    body = json.loads(pathlib.Path(written["result"]).read_text(encoding="utf-8"))
    return body["mutual_agreement"]["confirmed"]


def test_a_clean_series_is_confirmed(tmp_path) -> None:
    games = [_game(1, "capture", "Verified OK"), _game(2, "survival", "Verified OK")]
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.SURVIVAL)]

    assert _confirmed(tmp_path, games, outcomes) is True


def test_a_technical_ending_does_not_withdraw_agreement(tmp_path) -> None:
    """The regression. One timeout used to make the whole series unconfirmed."""
    games = [_game(1, "capture", "Verified OK"), _game(2, "timeout", "AUDIT SKIPPED")]
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.TIMEOUT)]

    assert _confirmed(tmp_path, games, outcomes) is True


def test_tampering_still_withdraws_it(tmp_path) -> None:
    """The flag must keep its teeth: a forged log is a real disagreement."""
    games = [_game(1, "capture", "Verified OK"), _game(2, "tamper_forfeit", "TAMPERED")]
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.TAMPER_FORFEIT)]

    assert _confirmed(tmp_path, games, outcomes) is False


def test_a_failed_audit_on_a_played_game_still_withdraws_it(tmp_path) -> None:
    """Only *technical* endings are excused; a played game owes us its reveal."""
    games = [_game(1, "capture", "AUDIT FAILED"), _game(2, "survival", "Verified OK")]
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.SURVIVAL)]

    assert _confirmed(tmp_path, games, outcomes) is False


def test_a_disputed_game_still_withdraws_it(tmp_path) -> None:
    """The other half of the rule, unchanged."""
    games = [_game(1, "capture", "Verified OK"), _game(2, "survival", "Verified OK")]
    games[1]["disputed"] = True
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.SURVIVAL)]

    assert _confirmed(tmp_path, games, outcomes) is False


def test_a_contradicted_game_is_reconciled_not_just_flagged(tmp_path) -> None:
    """`reconcile` is now the authority on the dispute half, and it is reached.

    It had no production caller — the flag it exists to set was derived from our
    own audits only, so `mutual_agreement.confirmed` was never a statement about
    agreement *with the opponent*.
    """
    games = [_game(1, "capture", "Verified OK"), _game(2, "survival", "Verified OK")]
    games[1]["disputed"] = True
    games[1]["their_claim"] = "capture"
    outcomes = [_outcome(1, EndReason.CAPTURE), _outcome(2, EndReason.SURVIVAL)]

    assert _confirmed(tmp_path, games, outcomes) is False


def test_a_mismatch_reaches_the_operator(tmp_path) -> None:
    """A wrong-but-confident report is worse than a late one.

    The alert carries both versions so a human can decide, which is the whole
    reason `reconcile` refuses to silently pick a winner.
    """
    from najamjad_agent.domain.series import SeriesResult
    from najamjad_agent.reporting.filing import MatchFiler

    events: list[dict] = []
    games = [_game(1, "survival", "Verified OK")]
    games[0]["disputed"] = True
    games[0]["their_claim"] = "capture"
    filer = MatchFiler(tmp_path, "najamjad-vs-rival", "uid-1", GROUPS, emit=events.append)
    filer.file_match(
        games,
        [_outcome(1, EndReason.SURVIVAL)],
        SeriesResult(
            total_score={"najamjad": 20, "rival": 5},
            sub_games_won={"najamjad": 1, "rival": 0},
            ties=0,
            winner_group="najamjad",
            series_tie=False,
        ),
        {},
        "sha",
        {"najamjad": {}, "rival": {}},
    )

    mismatch = [event for event in events if event["event"] == "result.mismatch"]
    assert mismatch, "a contradicted result reached nobody"
    assert mismatch[0]["differences"]


def test_a_silent_opponent_does_not_block_the_report(tmp_path) -> None:
    """`NO_REPLY` still files: rule 35 punishes not reporting, too."""
    games = [_game(1, "timeout", "AUDIT SKIPPED"), _game(2, "timeout", "AUDIT SKIPPED")]
    outcomes = [_outcome(1, EndReason.TIMEOUT), _outcome(2, EndReason.TIMEOUT)]

    assert _confirmed(tmp_path, games, outcomes) is True
