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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "opponents": opponents,
        "history": [{"opponent": name, "game_uid": name, "at": "", "count_after": index}
                    for index, name in enumerate(opponents, 1)],
    }), encoding="utf-8")


def test_agreeing_ledgers_pass_and_say_the_count(tmp_path: Path) -> None:
    ours, theirs = tmp_path / "a" / "counted.json", tmp_path / "b"
    _ledger(ours, ["uoh-ay26", "imreeyal"])
    _ledger(theirs / "workspace/counted_games.json", ["imreeyal", "uoh-ay26"])

    detail = counted_ledger_check(Manager(ours), sibling=theirs)()

    assert detail is not None and "2 counted" in detail


def test_a_divergent_sibling_fails_and_names_both_counts(tmp_path: Path) -> None:
    """The exact state found before the vibecode series."""
    ours, theirs = tmp_path / "a" / "counted.json", tmp_path / "b"
    _ledger(ours, ["uoh-ay26"])
    _ledger(theirs / "workspace/counted_games.json", ["uoh-ay26", "imreeyal"])

    with pytest.raises(ValueError) as caught:
        counted_ledger_check(Manager(ours), sibling=theirs)()

    message = str(caught.value)
    assert "declares 1" in message and "declares 2" in message
    assert "reconcile_counted" in message, "the failure must say how to fix it"


def test_a_missing_sibling_is_not_applicable_rather_than_a_failure(tmp_path: Path) -> None:
    """The repos are submitted standalone (ADR-002).

    A grader unpacking one of them alone has no sibling to compare against, and
    `preflight` must not go red for it — a probe returning `None` is recorded as
    not applicable.
    """
    ours = tmp_path / "a" / "counted.json"
    _ledger(ours, ["uoh-ay26"])

    assert counted_ledger_check(Manager(ours), sibling=tmp_path / "nowhere")() is None
