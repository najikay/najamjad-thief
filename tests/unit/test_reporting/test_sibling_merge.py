"""Rejoining a series two processes played half of each.

Book Appendix ה rule 1 splits the roles across two processes; rules 33-35 still
want one report per team covering all six mini-games, and void both teams when
the two reports disagree. Everything here guards that seam.
"""

from __future__ import annotations

from typing import Any

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SubGameOutcome
from najamjad_agent.reporting.sibling_merge import (
    assemble,
    clear_partials,
    partial_path,
    write_partial,
)

SCORING = {"scoring": {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5,
                       "survival_thief": 10, "tie_score": 2}}
GROUPS = ("najamjad", "rival")


class _Manager:
    def __init__(self, opening: str = "thief") -> None:
        self._values = {"game.opening_role": opening, "network_and_league.num_games": 6}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def section(self, _name: str) -> dict:
        return dict(SCORING["scoring"])


def _outcome(sub_game: int, role: Role) -> SubGameOutcome:
    return SubGameOutcome(sub_game=sub_game, role=role, end_reason=EndReason.CAPTURE,
                          our_score=20, their_score=5, steps=9)


def _half(numbers: list[int], role: Role) -> tuple[list[dict], list[SubGameOutcome]]:
    return ([{"sub_game": n, "role": role.value} for n in numbers],
            [_outcome(n, role) for n in numbers])


@pytest.fixture()
def table() -> ScoreTable:
    return ScoreTable.from_config(SCORING)


def _call(manager, our_role, games, outcomes, root, table, seen):
    return assemble(manager, our_role, "uid-1", games, outcomes, "untouched",
                    GROUPS, table, seen.append, root=root)


def test_an_unsplit_run_is_handed_back_exactly_as_it_arrived(tmp_path, table):
    """The single-process path must not change until the split is switched on."""
    games, outcomes = _half([1, 2, 3, 4, 5, 6], Role.COP)
    seen: list[dict] = []

    result = _call(_Manager(opening=""), Role.COP, games, outcomes, tmp_path, table, seen)

    assert result == (games, outcomes, "untouched")
    assert not (tmp_path / "workspace" / "partials").exists()


def test_the_process_that_does_not_hold_the_last_window_files_nothing(tmp_path, table):
    """Two reports on one series is the contradiction rules 33-35 void."""
    games, outcomes = _half([1, 3, 5], Role.THIEF)
    seen: list[dict] = []

    # Opening as thief, mini-game 6 belongs to the cop process — not this one.
    result = _call(_Manager(), Role.THIEF, games, outcomes, tmp_path, table, seen)

    assert result is None
    assert partial_path(tmp_path, "uid-1", Role.THIEF).exists()
    assert [event["event"] for event in seen] == ["series.sibling_files"]


def test_the_last_window_rejoins_both_halves_into_one_ordered_series(tmp_path, table):
    """Six mini-games, in order, scored as one series."""
    sibling = tmp_path / "najamjad-thief"
    here = tmp_path / "najamjad-cop"
    here.mkdir()
    theirs_games, theirs_outcomes = _half([1, 3, 5], Role.THIEF)
    write_partial(sibling, "uid-1", Role.THIEF, theirs_games, theirs_outcomes)
    ours_games, ours_outcomes = _half([2, 4, 6], Role.COP)
    seen: list[dict] = []

    games, outcomes, result = _call(
        _Manager(), Role.COP, ours_games, ours_outcomes, here, table, seen
    )

    assert [game["sub_game"] for game in games] == [1, 2, 3, 4, 5, 6]
    assert [outcome.sub_game for outcome in outcomes] == [1, 2, 3, 4, 5, 6]
    assert result.total_score == {"najamjad": 120, "rival": 30}


def test_a_half_written_before_our_own_first_window_is_still_this_attempt(tmp_path, table):
    """The two halves are parallel streams, so ours is not always the later.

    Found by the four-process rehearsal, twice, and each time it cost the whole
    point of the module. Our thief opened window 1, played it and wrote its
    half at 20:02:01; our own server had not finished binding until 20:02:07
    and our window 2 began after that. Both freshness checks tried — our first
    mini-game's `started_at`, then this process's start — read those six
    seconds of ordinary concurrency as a previous attempt, announced
    `sibling_half_missing`, and filed a two-game series as one game. That is
    precisely the rules 33-35 mismatch the merge exists to prevent, so no clock
    is compared here at all: see `clear_partials`.
    """
    sibling = tmp_path / "najamjad-thief"
    here = tmp_path / "najamjad-cop"
    here.mkdir()
    theirs_games, theirs_outcomes = _half([1, 3, 5], Role.THIEF)
    write_partial(sibling, "uid-1", Role.THIEF, theirs_games, theirs_outcomes)
    ours_games, ours_outcomes = _half([2, 4, 6], Role.COP)
    for game in ours_games:
        game["started_at"] = "2099-01-01T00:00:00+00:00"
    seen: list[dict] = []

    games, _, _ = assemble(
        _Manager(), Role.COP, "uid-1", ours_games, ours_outcomes, "x", GROUPS,
        table, seen.append, root=here, wait=0.0,
    )

    assert [game["sub_game"] for game in games] == [1, 2, 3, 4, 5, 6]
    assert "series.sibling_half_missing" not in [event["event"] for event in seen]


def test_a_process_clears_its_own_halves_and_never_its_siblings(tmp_path):
    """How an attempt is identified once no clock can do it.

    Each process drops what it wrote before it plays again, so a half found
    under the sibling's role belongs to the sibling's current run. Touching
    the sibling's file instead would be both wrong and a rule-2 problem: the
    only thing either process may act on is its own.
    """
    games, outcomes = _half([2, 4, 6], Role.COP)
    write_partial(tmp_path, "uid-old", Role.COP, games, outcomes)
    write_partial(tmp_path, "uid-1", Role.COP, games, outcomes)
    write_partial(tmp_path, "uid-1", Role.THIEF, *_half([1, 3, 5], Role.THIEF))
    seen: list[dict] = []

    dropped = clear_partials(tmp_path, Role.COP, seen.append)

    assert dropped == 2
    assert not partial_path(tmp_path, "uid-1", Role.COP).exists()
    assert partial_path(tmp_path, "uid-1", Role.THIEF).exists(), "never our sibling's"
    assert [event["event"] for event in seen] == ["series.partials_cleared"]


def test_a_missing_sibling_half_is_announced_and_never_passed_off_as_whole(tmp_path, table):
    """Filing three games as six understates us against their full report.

    The half must be *absent and said so*, not quietly treated as a complete
    series — that mismatch is what voids both teams.
    """
    here = tmp_path / "najamjad-cop"
    here.mkdir()
    ours_games, ours_outcomes = _half([2, 4, 6], Role.COP)
    seen: list[dict] = []

    games, _, _ = assemble(
        _Manager(), Role.COP, "uid-1", ours_games, ours_outcomes, "x", GROUPS,
        table, seen.append, root=here, wait=0.0,
    )

    assert [game["sub_game"] for game in games] == [2, 4, 6]
    events = [event["event"] for event in seen]
    assert "series.sibling_half_missing" in events
    assert [e for e in seen if e["event"] == "series.rejoined"][0]["sibling_half"] is False
