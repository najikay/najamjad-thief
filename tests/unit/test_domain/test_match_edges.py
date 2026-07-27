"""The match runner's edge paths — the ones that only happen when it matters.

A peer that goes quiet at audit time, and a game nobody manages to end. Both are
exactly the situations where crashing or hanging would convert the opponent's
problem into our technical loss, so both get a verdict instead.
"""

from najamjad_agent.constants import EndReason, Move, Role
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.match_audit import exchange_audit, receive_reveal
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker
from tests.fakes.orchestration import FakeClock, FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING


class SilentPeer:
    """A peer that takes our reveal and gives nothing back."""

    def __init__(self) -> None:
        self.received: list = []

    def send_audit(self, payload) -> None:
        self.received.append(payload)

    def receive_audit(self, timeout):
        return None


class ListPeer(SilentPeer):
    """A peer that answers with a bare list rather than the usual envelope."""

    def receive_audit(self, timeout):
        return []


def test_a_peer_that_reveals_nothing_fails_the_audit_rather_than_crashing():
    """Silence at audit time is a common shape of cheating (rules 18-20)."""
    report = receive_reveal(SilentPeer(), timeout=0.01)

    assert report.passed is False
    assert "revealed nothing" in report.errors[0]


def test_we_reveal_our_own_records_even_to_a_silent_peer():
    """Withholding ours would be indistinguishable from preparing to forge."""
    state = build_state(Role.COP)
    state.ledger.commit(1, {"step": 1, "move": "MOVE:S"})
    peer = SilentPeer()

    exchange_audit(state.ledger, peer, timeout=0.01, sender="police")

    assert peer.received, "our reveal must go out even if theirs never comes"
    assert len(peer.received[0]["records"]) == 1


def test_the_reveal_is_enveloped_the_way_the_wire_schema_declares():
    """The bug this shape exists for: we sent a bare list, the peer's validator
    rejected it, the reveal never arrived, and both sides recorded TAMPERED for
    a game neither had cheated in. Only the fake transport wrapped it."""
    from najamjad_agent.protocol.schemas_wire import AuditPayload

    state = build_state(Role.COP)
    state.ledger.commit(1, {"step": 1, "move": "MOVE:S"})
    peer = SilentPeer()

    exchange_audit(state.ledger, peer, timeout=0.01, sender="police")

    # Parses as the wire schema — which a bare list does not.
    parsed = AuditPayload.model_validate(peer.received[0])
    assert parsed.sender == "police"
    assert len(parsed.records) == 1


def test_an_audit_reply_without_the_usual_envelope_is_still_read():
    """Another team may send the bare list; that is a container difference,
    not a reason to call an honest peer a cheat."""
    report = receive_reveal(ListPeer(), timeout=0.01)

    assert report.passed is False  # empty, so nothing verifies — but no crash


def test_a_game_nobody_ends_stops_at_the_move_limit():
    """The turn loop is bounded, so a peer answering forever cannot hold us."""
    state = build_state(Role.COP)

    class Quiet:
        def send_turn(self, message): ...
        def reset(self): ...
        def receive_turn(self, timeout):
            return None
        def send_audit(self, payload): ...
        def receive_audit(self, timeout):
            return None

    runner = MatchRunner(
        params=state.board.params,
        tracker=SeriesTracker("us", "them", ScoreTable.from_config(SCORING), Role.COP, 1),
        transport=Quiet(),
        build_state=lambda _p, role, _sg: build_state(role),
        build_brain=lambda _role, _state: ScriptedBrain([Move.STAY] * 200),
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        response_timeout=0.001,
        max_retries=1,
        audit_timeout=0.001,
    )

    record = runner.play_sub_game(1, Role.COP)

    assert record["end_reason"] in {reason.value for reason in EndReason}
    assert runner.tracker.is_complete
