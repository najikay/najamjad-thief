"""A full six-game series, both peers driven by the real match runner.

This is the piece that was missing: every component existed, but nothing played
a match. Here two `MatchRunner`s face each other across a linked transport,
alternating roles per the book, auditing after every mini-game.

The assertions are the E21 exit criteria — every game audits clean, roles
alternate, the series scores out, and both sides agree on what happened.
"""

import threading

import pytest

from najamjad_agent.constants import EndReason, Move, Role
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker, role_for
from tests.fakes.network import linked_pair
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING

CYCLE = [Move.SOUTH, Move.EAST, Move.NORTH, Move.WEST]


def build_runner(link, our_group: str, their_group: str, first_role: Role) -> MatchRunner:
    """A runner wired entirely to fakes except the rules themselves."""
    state = build_state(Role.COP)
    tracker = SeriesTracker(
        our_group=our_group,
        their_group=their_group,
        table=ScoreTable.from_config(SCORING),
        first_role=first_role,
    )
    return MatchRunner(
        params=state.board.params,
        tracker=tracker,
        transport=link,
        build_state=lambda _params, role, sub_game: _fresh_state(role, sub_game),
        build_brain=lambda _role, _state: ScriptedBrain(CYCLE * 40),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        first_role=first_role,
        # Short deadlines keep the suite quick. They also make a regression
        # loud: if a peer ever stops answering again, this test hangs for
        # seconds rather than the ninety a production timeout would take.
        response_timeout=0.3,
        max_retries=2,
        audit_timeout=5.0,
    )


def _fresh_state(role: Role, sub_game: int):
    """A new board per mini-game; nothing may leak between games."""
    state = build_state(role)
    state.sub_game = sub_game
    return state


def play_pair(cop_first: MatchRunner, thief_first: MatchRunner) -> None:
    """Run both peers concurrently — each blocks waiting for the other."""
    errors: list[BaseException] = []

    def drive(runner: MatchRunner) -> None:
        try:
            runner.play_series()
        except BaseException as failure:  # noqa: BLE001 - re-raised in the test thread
            errors.append(failure)

    threads = [threading.Thread(target=drive, args=(runner,)) for runner in (cop_first, thief_first)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert not any(thread.is_alive() for thread in threads), "a peer never finished its series"
    if errors:
        raise errors[0]


@pytest.fixture()
def played() -> tuple[MatchRunner, MatchRunner]:
    """Two peers that have played a complete series against each other."""
    left, right = linked_pair()
    ours = build_runner(left, "najamjad", "opponent", Role.COP)
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)
    play_pair(ours, theirs)
    return ours, theirs


@pytest.mark.slow
def test_a_full_series_completes_for_both_peers(played):
    ours, theirs = played

    assert ours.tracker.is_complete
    assert theirs.tracker.is_complete
    assert len(ours.games) == len(theirs.games) == 6


@pytest.mark.slow
def test_every_mini_game_audits_clean(played):
    """T-2103, goal G4: an honest series must verify end to end."""
    ours, theirs = played

    assert [game["audit"] for game in ours.games] == ["Verified OK"] * 6
    assert [game["audit"] for game in theirs.games] == ["Verified OK"] * 6


@pytest.mark.slow
def test_roles_alternate_and_are_opposite_between_peers(played):
    """Book Table 5: roles swap each mini-game, and we are never both the cop."""
    ours, theirs = played

    our_roles = [game["role"] for game in ours.games]
    their_roles = [game["role"] for game in theirs.games]

    assert our_roles == [role_for(n, Role.COP).value for n in range(1, 7)]
    assert all(a != b for a, b in zip(our_roles, their_roles, strict=True))


@pytest.mark.slow
def test_the_series_produces_a_scored_result(played):
    ours, _theirs = played

    result = ours.tracker.result()

    assert sum(outcome.our_score for outcome in ours.tracker.outcomes) >= 0
    assert result.total_score["najamjad"] + result.total_score["opponent"] > 0


@pytest.mark.slow
def test_both_peers_agree_on_how_each_game_ended(played):
    """T-2105 in spirit: a disagreement here voids the game for both (rule 35).

    This failed before the capture answer was wired: the thief recorded a
    capture and the cop, never told whether its claim landed, waited out the
    deadline and recorded a timeout for the same mini-game.
    """
    ours, theirs = played

    for ours_game, theirs_game in zip(ours.games, theirs.games, strict=True):
        assert ours_game["sub_game"] == theirs_game["sub_game"]
        assert ours_game["end_reason"] == theirs_game["end_reason"]


@pytest.mark.slow
def test_the_captured_thief_answers_before_the_game_closes(played):
    """Rules 21-22. The answering turn is one extra sealed step, so the thief's
    record is exactly one longer — never more, never fewer."""
    ours, theirs = played

    for ours_game, theirs_game in zip(ours.games, theirs.games, strict=True):
        if ours_game["end_reason"] != "capture":
            continue
        thief, cop = sorted((ours_game, theirs_game), key=lambda g: g["role"] == "police")
        assert thief["steps"] - cop["steps"] == 1


@pytest.mark.slow
def test_no_mini_game_runs_past_the_agreed_move_limit(played):
    """A peer answering forever must not keep us in a decided game."""
    ours, _theirs = played
    limit = ours.params.max_moves

    assert all(game["steps"] <= limit for game in ours.games)


@pytest.mark.slow
def test_every_game_ends_for_a_declared_reason(played):
    ours, _theirs = played
    allowed = {reason.value for reason in EndReason}

    assert {game["end_reason"] for game in ours.games} <= allowed
