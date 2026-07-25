"""Fault injection — a peer that stops answering, and stale/replayed turns.

The commonest way a league match dies: silence. The bar is that we never hang,
always produce verifiable evidence of what we waited for, and resolve the game
through a documented path.
"""


from najamjad_agent.constants import EndReason, Phase, Role
from najamjad_agent.domain.crypto import verify
from najamjad_agent.net.deadline import DeadlineTracker
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.peer_transport import PeerTransport
from tests.fakes.orchestration import build_orchestrator

TURN = {"step": 1, "sender": "rival", "commit": "a" * 64, "hint": "somewhere"}


class DeadClient:
    """A peer that is simply not there."""

    def send(self, kind: str, payload: dict) -> None:
        raise ConnectionError("connection refused")

    def try_send(self, kind: str, payload: dict) -> bool:
        return False


class FlakyClient:
    """Drops the first N sends, then recovers — a mid-turn disconnect."""

    def __init__(self, failures: int) -> None:
        self.remaining = failures
        self.delivered: list[tuple[str, dict]] = []

    def send(self, kind: str, payload: dict) -> None:
        if self.remaining > 0:
            self.remaining -= 1
            raise ConnectionResetError("connection dropped mid-send")
        self.delivered.append((kind, payload))

    def try_send(self, kind: str, payload: dict) -> bool:
        try:
            self.send(kind, payload)
        except ConnectionResetError:
            return False
        return True


def _transport(client, events: list[dict], timeout: float = 0.02) -> tuple[PeerTransport, Inboxes]:
    inboxes = Inboxes(emit=events.append)
    tracker = DeadlineTracker(response_timeout=timeout, max_retries=2, emit=events.append)
    return PeerTransport(inboxes, client, tracker, emit=events.append), inboxes


def test_silent_opponent_resolves_to_a_clean_technical_loss() -> None:
    """The commonest league failure: a peer that stops answering."""
    events: list[dict] = []
    transport, _ = _transport(DeadClient(), events)
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, response_timeout=0.02, max_retries=2
    )
    orchestrator._transport = transport

    assert orchestrator.receive_turn() is EndReason.TIMEOUT
    assert orchestrator.fsm.phase is Phase.TECHNICAL_LOSS
    assert any(event["event"] == "deadline.timeout" for event in events)


def test_a_timeout_produces_verifiable_evidence() -> None:
    """Better than the reference's unverifiable self-awarded win."""
    events: list[dict] = []
    tracker = DeadlineTracker(response_timeout=0.01, max_retries=2, emit=events.append)
    inboxes = Inboxes(emit=events.append)
    transport = PeerTransport(inboxes, DeadClient(), tracker, emit=events.append)

    assert transport.receive_turn(timeout=0.01) is None
    record = tracker.evidence(step=7, role="police", sub_game=1)
    assert verify(record.payload, record.nonce, record.commit)
    assert record.payload["timeouts"][0]["label"] == "opponent-turn"
