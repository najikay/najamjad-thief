"""The counted count must be the same number in both repos before a match.

A series is played from whichever repo we open the role on, and only that
repo's tracker is written at settlement. On 2026-08-14 `najamjad-cop` declared
1 counted match and `najamjad-thief` declared 2, having played both — so the
vibecode series, opened as cop, would have gone out under a false figure. Rule
38 judges counted declarations on mutual consistency between the two teams'
files, and imreeyal's artifact already says two.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from najamjad_agent.net.preflight_checks import counted_ledger_check


class Manager:
    """Just enough config for the probe."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, dotted: str, default: object = None) -> object:
        return str(self._path) if dotted == "paths.counted_games" else default


def _ledger(path: Path, opponents: list[str]) -> None:
    """Write a ledger holding `opponents`.

    The names are deliberately **placeholders**. Real team names belong where the
    data is real — `tests/regression/scripted_opponents.py` holds lines opponents
    actually played, and the archives and docs record what actually happened.
    Invented fixture data carrying a real name reads as a claim about that team's
    ledger, and these repos get read by the teams in question (rule 49).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "opponents": opponents,
        "history": [{"opponent": name, "game_uid": name, "at": "", "count_after": index}
                    for index, name in enumerate(opponents, 1)],
    }), encoding="utf-8")


def test_agreeing_ledgers_pass_and_say_the_count(tmp_path: Path) -> None:
    ours, theirs = tmp_path / "a" / "counted.json", tmp_path / "b"
    _ledger(ours, ["peer-one", "peer-two"])
    _ledger(theirs / "workspace/counted_games.json", ["peer-two", "peer-one"])

    detail = counted_ledger_check(Manager(ours), sibling=theirs)()

    assert detail is not None and "declaring 2 counted" in detail


def test_a_divergent_sibling_fails_and_names_both_counts(tmp_path: Path) -> None:
    """The exact state found before the vibecode series."""
    ours, theirs = tmp_path / "a" / "counted.json", tmp_path / "b"
    _ledger(ours, ["peer-one"])
    _ledger(theirs / "workspace/counted_games.json", ["peer-one", "peer-two"])

    with pytest.raises(ValueError) as caught:
        counted_ledger_check(Manager(ours), sibling=theirs)()

    message = str(caught.value)
    assert "declares 1" in message and "declares 2" in message
    assert "reconcile_counted" in message, "the failure must say how to fix it"


def test_a_missing_sibling_still_reports_the_count_it_would_declare(tmp_path: Path) -> None:
    """Standalone is the CI environment, and the check must still prove something.

    The repos are submitted standalone (ADR-002), so a grader — and CI — has no
    sibling to compare against. The first version returned `None` here, which
    `run_preflight` records as *not applicable*, and
    `test_every_check_actually_proves_something` failed both repos' CI for it.
    That test was right: only `tunnel` may prove nothing, and a check that goes
    silent in the one environment where it always runs is decoration. Reading
    the ledger and naming the figure about to go on the wire is itself proof.
    """
    ours = tmp_path / "a" / "counted.json"
    _ledger(ours, ["peer-one"])

    detail = counted_ledger_check(Manager(ours), sibling=tmp_path / "nowhere")()

    assert detail, "a probe returning None is recorded as 'not applicable'"
    assert "declaring 1 counted" in detail
    assert "no sibling" in detail
