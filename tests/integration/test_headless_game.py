"""Headless end-to-end: two orchestrators play real mini-games face to face.

This is the M2 exit criterion. Both peers run the full production turn loop —
belief, strategy filter, commit-reveal, physics policing, scent decay — wired to
each other through an in-memory transport. Nothing about the game rules is
faked; only the network and the clock are.
"""

import pytest

from najamjad_agent.constants import EndReason, Move, Phase, Role
from najamjad_agent.domain.audit import audit_records, may_agree_result
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.fsm import GameStateMachine
from najamjad_agent.domain.orchestrator import Orchestrator
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker, role_for
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state

SCORING = {
    "scoring": {
        "capture_cop": 20,
        "capture_thief": 5,
        "survival_cop": 5,
        "survival_thief": 10,
        "tie_score": 2,
    }
}


class LinkedTransport:
    """An in-memory link: what one peer sends, the other receives."""

    def __init__(self) -> None:
        self.outbox: list[dict] = []
        self.peer: LinkedTransport | None = None
        self.audit_inbox: list[dict] = []

    def connect(self, other: "LinkedTransport") -> None:
        self.peer = other
        other.peer = self

    def send_turn(self, message: dict) -> None:
        assert self.peer is not None
        self.peer.outbox.append(message)

    def receive_turn(self, timeout: float) -> dict | None:
        """One message per turn now: the commitment plus public evidence."""
        return self.outbox.pop(0) if self.outbox else None

    def send_audit(self, payload: dict) -> None:
        assert self.peer is not None
        self.peer.audit_inbox.append({"records": payload})

    def receive_audit(self, timeout: float) -> dict | None:
        return self.audit_inbox.pop(0) if self.audit_inbox else None


def _peer(role: Role, moves: list[Move], transport: LinkedTransport, position=None) -> Orchestrator:
    state = build_state(role, position=position)
    fsm = GameStateMachine(game_uid="headless")
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    return Orchestrator(
        state=state,
        fsm=fsm,
        transport=transport,
        brain=ScriptedBrain(moves),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
    )


def _play(cop: Orchestrator, thief: Orchestrator, turns: int) -> EndReason | None:
    """Run strict ping-pong: thief moves first (reference-compatible order)."""
    for _ in range(turns):
        for actor, other in ((thief, cop), (cop, thief)):
            ended = actor.take_turn()
            if ended:
                return ended
            ended = other.receive_turn()
            if ended:
                return ended
    return None


@pytest.fixture()
def link() -> tuple[LinkedTransport, LinkedTransport]:
    left, right = LinkedTransport(), LinkedTransport()
    left.connect(right)
    return left, right


def test_two_peers_play_a_clean_mini_game(link) -> None:
    cop_link, thief_link = link
    cop = _peer(Role.COP, [Move.SOUTH] * 4, cop_link)
    thief = _peer(Role.THIEF, [Move.SOUTH] * 4, thief_link)

    _play(cop, thief, turns=3)

    assert cop.state.step == 3
    assert thief.state.step == 3
    assert cop.state.own_position == (3, 0)
    assert thief.state.own_position == (6, 3)


def test_each_peer_tracks_the_other_from_scent_alone(link) -> None:
    """No position is transmitted, so tracking must come from the trail."""
    cop_link, thief_link = link
    cop = _peer(Role.COP, [Move.SOUTH] * 4, cop_link)
    thief = _peer(Role.THIEF, [Move.EAST] * 4, thief_link)

    _play(cop, thief, turns=3)

    assert cop.state.opponent_scent.intensity_at(thief.state.own_position) > 0
    assert cop.state.belief.peak() is not None
    assert cop.state.opponent_estimate == cop.state.belief.peak()
    assert Board.manhattan(cop.state.belief.peak(), thief.state.own_position) <= 2


def test_full_game_audits_clean_on_both_sides(link) -> None:
    """The whole point of the loop: an honest game ends in Verified OK."""
    cop_link, thief_link = link
    cop = _peer(Role.COP, [Move.SOUTH] * 4, cop_link)
    thief = _peer(Role.THIEF, [Move.EAST] * 4, thief_link)

    _play(cop, thief, turns=3)
    cop.state.ledger.open_audit()
    thief.state.ledger.open_audit()

    cop_report = audit_records(cop.state.ledger.audit_payload())
    thief_report = audit_records(thief.state.ledger.audit_payload())
    assert cop_report.banner == "Verified OK"
    assert thief_report.banner == "Verified OK"
    assert may_agree_result(cop_report, thief_report)


def test_scent_decay_stays_in_step_between_peers(link) -> None:
    """Both sides must age the world identically or beliefs diverge."""
    cop_link, thief_link = link
    cop = _peer(Role.COP, [Move.SOUTH] * 4, cop_link)
    thief = _peer(Role.THIEF, [Move.EAST] * 4, thief_link)

    _play(cop, thief, turns=3)

    assert cop.state.full_turns == thief.state.full_turns


def test_capture_ends_the_game_and_scores_the_series(link) -> None:
    """The cop claims the cell it stands on; the thief answers honestly."""
    cop_link, thief_link = link
    cop = _peer(Role.COP, [Move.STAY], cop_link, position=(3, 2))
    thief = _peer(Role.THIEF, [Move.STAY], thief_link, position=(3, 3))
    cop.state.opponent_estimate = (3, 3)

    cop._brain = ScriptedBrain([Move.EAST])
    thief.take_turn()
    cop.receive_turn()
    cop.state.opponent_estimate = (3, 3)
    cop.take_turn()
    ended = thief.receive_turn()

    assert ended is EndReason.CAPTURE
    tracker = SeriesTracker("najamjad", "rival", ScoreTable.from_config(SCORING), Role.COP)
    outcome = tracker.record(ended, Role.THIEF, steps=thief.state.step)
    assert (outcome.our_score, outcome.their_score) == (5, 20)


def test_series_of_six_alternating_games_aggregates(link) -> None:
    """M2 exit: a full 6-game series with role swaps and aggregate scoring."""
    tracker = SeriesTracker("najamjad", "rival", ScoreTable.from_config(SCORING), Role.COP)

    for number in range(1, 7):
        our_role = role_for(number, Role.COP)
        cop_link, thief_link = LinkedTransport(), LinkedTransport()
        cop_link.connect(thief_link)
        cop = _peer(Role.COP, [Move.SOUTH] * 3, cop_link)
        thief = _peer(Role.THIEF, [Move.EAST] * 3, thief_link)

        _play(cop, thief, turns=2)
        ours = cop if our_role is Role.COP else thief
        assert ours.state.step == 2, "each mini-game starts from clean state"
        tracker.record(EndReason.SURVIVAL, our_role, steps=ours.state.step)

    assert tracker.is_complete
    result = tracker.result()
    assert result.total_score == {"najamjad": 45, "rival": 45}
    assert result.series_tie is True
