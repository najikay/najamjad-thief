"""Chaos at match level: what happens when the opponent misbehaves mid-series.

The existing fault tests exercise one mini-game through the orchestrator. These
exercise the *series* — the layer that is newest and where the ending-agreement
defects lived. The rule throughout: an opponent's failure must become a clean
recorded outcome for us, never a hang and never a crash. Their problem must not
be convertible into our technical loss.
"""

import threading

import pytest

from najamjad_agent.constants import EndReason, Move, Role
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker
from tests.fakes.network import BlockingLink, linked_pair
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING

MOVES = [Move.SOUTH, Move.EAST, Move.NORTH, Move.WEST] * 60


def runner(link, role: Role, games: int = 2) -> MatchRunner:
    """A peer wired to fakes, with deadlines short enough to keep tests quick."""
    state = build_state(Role.COP)
    return MatchRunner(
        params=state.board.params,
        tracker=SeriesTracker("us", "them", ScoreTable.from_config(SCORING), role, games),
        transport=link,
        build_state=lambda _p, for_role, _sg: build_state(for_role),
        build_brain=lambda _role, _state: ScriptedBrain(list(MOVES)),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        first_role=role,
        response_timeout=0.15,
        max_retries=2,
        audit_timeout=0.3,
    )


def play(*runners: MatchRunner, timeout: float = 90) -> list[BaseException]:
    """Run peers concurrently; return anything they raised."""
    errors: list[BaseException] = []

    def drive(peer: MatchRunner) -> None:
        try:
            peer.play_series()
        except BaseException as failure:  # noqa: BLE001 - surfaced to the test
            errors.append(failure)

    threads = [threading.Thread(target=drive, args=(peer,), daemon=True) for peer in runners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)
    assert not any(thread.is_alive() for thread in threads), "a peer hung instead of resolving"
    return errors


def test_an_opponent_that_crashes_mid_series_leaves_us_with_a_clean_result():
    """T-2114. They vanish after game one; we must finish and record, not hang."""
    left, right = linked_pair()
    ours, theirs = runner(left, Role.COP, games=2), runner(right, Role.THIEF, games=1)

    errors = play(ours, theirs)

    assert not errors, f"a crashed opponent raised into our loop: {errors}"
    assert ours.tracker.is_complete, "we must still complete our own series"
    assert len(ours.games) == 2
    assert ours.games[-1]["end_reason"] in {reason.value for reason in EndReason}


def test_an_opponent_that_never_speaks_at_all_resolves_without_hanging():
    """The peer is reachable but silent — the deadline path must carry us."""
    ours = runner(BlockingLink(), Role.COP, games=1)
    ours._transport.peer = ours._transport  # a link to nowhere but itself

    errors = play(ours, timeout=30)

    assert not errors
    assert ours.games[0]["end_reason"] == EndReason.TIMEOUT.value


def test_a_peer_that_stops_revealing_still_lets_us_record_the_game():
    """Silence at audit is not forgery, and must not be recorded as one.

    `TAMPERED` is an accusation: under rule 19 it voids the game for the
    accused. An opponent who never answered has proved nothing except that they
    stopped talking, and the end reason already records that. We reached this
    state once from a plain *disagreement* — they were still waiting for a move
    while we thought the game was over — and called them forgers for it.
    """
    left, right = linked_pair()
    ours, theirs = runner(left, Role.COP, games=1), runner(right, Role.THIEF, games=1)
    original = theirs._transport.send_audit
    theirs._transport.send_audit = lambda payload: None  # they simply never reveal

    errors = play(ours, theirs)

    assert not errors
    assert ours.games[0]["audit"] != "TAMPERED", "silence is not evidence of forgery"
    assert ours.games[0]["audit"] == "AUDIT SKIPPED"
    assert original is not None


@pytest.mark.parametrize("garbage", [{}, {"step": "soon"}, {"commit": None}, {"hint": [1, 2]}])
def test_garbage_turns_injected_mid_series_never_crash_the_loop(garbage):
    """A hostile peer may send anything; we answer with a verdict, not a stack."""
    left, right = linked_pair()
    ours = runner(left, Role.COP, games=1)
    for _ in range(5):
        left.turns.put(garbage)

    errors = play(ours, timeout=30)

    assert not errors
    assert ours.games, "the mini-game must still be recorded"


def test_a_series_survives_the_opponent_restarting_its_numbering():
    """A peer that restarts mid-series replays step 1; we must not accept it as
    history nor die on it."""
    left, right = linked_pair()
    ours, theirs = runner(left, Role.COP, games=1), runner(right, Role.THIEF, games=1)
    for _ in range(3):
        left.turns.put({"step": 1, "sender": "thief", "commit": "a" * 64})

    errors = play(ours, theirs)

    assert not errors
    assert len(ours.games) == 1
