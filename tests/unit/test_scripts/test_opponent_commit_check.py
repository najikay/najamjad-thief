"""A commit a team messages us is only worth having if something checks it.

Their commit reaches the result artifact on its own — it rides in their step-0
record and `peer_declaration.peer_facts` reads it — so none of this is needed to
*file* a match. What was missing was the control: the hash they send in a message
sat in the card's free-text `notes`, which no code has ever read, so there was
nothing to compare their declaration against.

Two bugs found while wiring it, both of the same shape — a check that answers
confidently about the wrong thing:

* reading `logs[0]` picked our own self-play rehearsal, which sorts first in a
  match-day archive, and reported **our** thief's commit as the opponent's;
* reading one commit per series is wrong for a role-split opponent. vibecode run
  two processes from two checkouts: their thief declared `ee853d79…` and their
  cop `1ab98583…` across the same six sub-games.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_opponent import check_commit, declared_commits  # noqa: E402

COP = "1ab98583e69b7046a48a0e14f3d9b5691d03062d"
THIEF = "ee853d79f0fed2fb4e947ba9c246c51d1ab06470"
OURS = "b42b31262162049022a346be024defc88cb2448f"


def _log(path: Path, game_id: str, role: str, commit: str) -> Path:
    path.write_text(json.dumps({
        "game_id": game_id,
        "opponent_records": [
            {"payload": {"type": "step_zero", "step": 0, "role": role,
                         "github_commit": commit}},
        ],
    }), encoding="utf-8")
    return path


def test_each_role_is_read_separately(tmp_path: Path) -> None:
    """A role-split opponent is two processes, and may be two checkouts."""
    logs = [
        _log(tmp_path / "log_us-vs-them_g01.json", "us-vs-them", "thief", THIEF),
        _log(tmp_path / "log_us-vs-them_g02.json", "us-vs-them", "police", COP),
    ]

    assert declared_commits(logs, "them") == {"thief": THIEF, "cop": COP}


def test_our_own_rehearsal_logs_are_not_mistaken_for_theirs(tmp_path: Path) -> None:
    """The bug: a match-day archive holds self-play beside the series, and it
    sorts first. `logs[0]` reported our own commit as the opponent's — a check
    that cannot tell us from them is worse than no check, because it produces a
    confident answer about the wrong team."""
    logs = [
        _log(tmp_path / "log_us-vs-us_g01.json", "us-vs-us", "thief", OURS),
        _log(tmp_path / "log_us-vs-them_g01.json", "us-vs-them", "thief", THIEF),
    ]

    assert declared_commits(logs, "them") == {"thief": THIEF}


def test_a_matching_commit_is_reported_as_matching() -> None:
    card = {"armed_commits": {"cop": COP}}

    assert "matches what they told us" in check_commit(card, {"cop": COP}, "cop")


def test_a_mismatch_names_both_hashes_and_the_rule() -> None:
    """Evidence, not a verdict: the likeliest cause is an honest push."""
    card = {"armed_commits": {"cop": COP}}

    note = check_commit(card, {"cop": THIEF}, "cop")

    assert "MISMATCH" in note and COP in note and THIEF in note
    assert "rule 53" in note
    assert "ask before assuming" in note, "a finding must not read as an accusation"


def test_no_expectation_reports_what_they_declared_rather_than_failing() -> None:
    """The normal case. A check that goes red when we simply never asked for a
    hash teaches people to ignore it."""
    note = check_commit({}, {"cop": COP}, "cop")

    assert "none on record" in note and COP in note
