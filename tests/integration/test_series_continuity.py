"""A series must survive the gap between mini-games (T-2101, T-2102).

Both defects here were found by running two real OS processes, and neither was
visible to any in-process test. They share a shape: state that is correct
*within* one mini-game and wrong *between* two.

The first ended every real series after game 1. The production inbox refuses a
step it has already accepted — the right behaviour against a replay — but each
mini-game restarts numbering at 1, so game 2's opening turn arrived as "step 1,
stale, last accepted was 11" and both peers then waited each other out until the
match died. Six mini-games are a series; one is nothing.

It survived 1,700 tests because `BlockingLink` had no sequence guard at all. The
fake has one now, so this class of defect fails in-process from here on.
"""

import pytest

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.sdk.bootstrap import shared_config_for

TURN = {"sender": "them", "hint": "x", "smell_grid": {}}


def turn(step: int) -> dict:
    """A minimally valid turn message at `step`."""
    return {**TURN, "step": step, "commit": f"{step:064d}"}


class RecordingTransport:
    """Counts resets and refuses to be reset mid-game."""

    def __init__(self) -> None:
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def send_turn(self, message): ...
    def receive_turn(self, timeout): return None
    def send_audit(self, payload): ...
    def receive_audit(self, timeout): return None


# --------------------------------------------------------------- the guard itself


def test_the_inbox_rejects_a_replayed_step_within_a_game():
    """The behaviour that is correct and must not be lost to the fix."""
    inboxes = Inboxes()

    assert inboxes.accept("turn", turn(1)).errors == []
    assert inboxes.accept("turn", turn(5)).errors == []
    replayed = inboxes.accept("turn", turn(5))

    assert replayed.errors and "stale or replayed" in replayed.errors[0]


def test_the_same_guard_rejects_the_next_mini_game_until_the_transport_resets():
    """The defect itself, in the production class.

    Game 1 ends at step 11; game 2 opens at step 1. Without a reset the guard
    reads that as a replay and the series stops after one mini-game.
    """
    inboxes = Inboxes()
    for step in range(1, 12):
        assert inboxes.accept("turn", turn(step)).errors == []

    blocked = inboxes.accept("turn", turn(1))
    assert blocked.errors, "this is what killed every real series after game 1"
    assert "last accepted was 11" in blocked.errors[0]

    inboxes.drain()

    assert inboxes.accept("turn", turn(1)).errors == [], "game 2 must be playable"


def test_draining_also_clears_a_turn_that_arrived_after_the_game_ended():
    """A late turn belongs to a finished game and must not open the next one."""
    inboxes = Inboxes()
    inboxes.accept("turn", turn(1))

    inboxes.drain()

    assert inboxes.poll("turn", timeout=0.01) is None


# --------------------------------------------------------------- the runner calls it


@pytest.mark.slow
def test_the_runner_resets_the_transport_once_per_mini_game():
    """The fix has to be *invoked*, not merely available."""
    from najamjad_agent.constants import Role
    from najamjad_agent.domain.match import MatchRunner
    from najamjad_agent.domain.scoring import ScoreTable
    from najamjad_agent.domain.series import SeriesTracker
    from tests.fakes.orchestration import FakeClock, FixedSpeaker, build_state
    from tests.integration.test_headless_game import SCORING

    transport = RecordingTransport()
    runner = MatchRunner(
        params=build_state(Role.COP).board.params,
        tracker=SeriesTracker(
            our_group="us", their_group="them", table=ScoreTable.from_config(SCORING),
            first_role=Role.COP, total_games=3,
        ),
        transport=transport,
        build_state=lambda _p, role, sub: build_state(role),
        build_brain=lambda _role, state: _Still(),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        first_role=Role.COP,
        response_timeout=0.01,
        max_retries=1,
        audit_timeout=0.01,
    )

    runner.play_series()

    assert transport.resets == 3, "one reset per mini-game, before it starts"


class _Still:
    """A brain that never moves; the peer's silence ends each game."""

    def pick_move(self, _facts):
        from najamjad_agent.constants import Move

        return Move.STAY

    def pick_barrier(self, _facts):
        return None


# --------------------------------------------------------------- the config seam


def test_a_per_match_config_directory_brings_its_own_agreed_terms(tmp_path):
    """`--config <dir>/police` must load `<dir>/game.json`.

    It used to load the repository's `config/game.json` regardless, so a
    per-opponent directory would pair that match's private settings with our
    *opening proposal* instead of the terms we actually agreed.
    """
    match_dir = tmp_path / "match-vs-them"
    (match_dir / "police").mkdir(parents=True)
    (match_dir / "game.json").write_text("{}", encoding="utf-8")

    assert shared_config_for(match_dir / "police") == match_dir / "game.json"


def test_the_repository_default_is_used_when_no_terms_sit_beside_the_config(tmp_path):
    """A private config on its own still boots against the committed terms."""
    lonely = tmp_path / "police"
    lonely.mkdir(parents=True)

    assert shared_config_for(lonely).name == "game.json"
    assert shared_config_for(lonely).parent.name == "config"
