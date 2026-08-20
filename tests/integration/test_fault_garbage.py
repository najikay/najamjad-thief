"""Fault injection — malformed payload bursts and queue hygiene.

A buggy or hostile peer must not be able to poison our state or crash us, and
recovery matters more than rejection: the next valid turn has to work.
"""

import pytest

from najamjad_agent.constants import Role
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


@pytest.mark.parametrize(
    "garbage",
    [
        {"step": "not-a-number", "commit": "c"},
        {"commit": ""},
        {"step": -5, "commit": "c" * 64},
        {"step": 1, "commit": "c" * 64, "smell_grid": "not-a-map"},
        {"step": 1, "commit": "c" * 64, "barrier_placed": [1, 2, 3]},
        {},
        [],
        "a string",
        None,
    ],
)
def test_malformed_payload_burst_never_reaches_the_game(garbage) -> None:
    """A flood of garbage must leave the queues clean and the agent alive."""
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    for _ in range(5):
        result = inboxes.accept("turn", garbage)
        assert not result.ok
        assert result.errors
    assert inboxes.pending("turn") == 0
    assert all(event["event"] != "inbox.accepted" for event in events)


def test_the_agent_still_plays_after_a_garbage_burst() -> None:
    """Recovery matters more than rejection: the next valid turn must work."""
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    for _ in range(20):
        inboxes.accept("turn", {"junk": True})
    assert inboxes.accept("turn", TURN).ok
    assert inboxes.pending("turn") == 1


def test_replayed_turns_leave_the_game_state_untouched() -> None:
    events: list[dict] = []
    transport, inboxes = _transport(DeadClient(), events)
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, response_timeout=0.02, max_retries=1
    )
    orchestrator._transport = transport

    inboxes.accept("turn", {**TURN, "hint": "by the river", "smell_grid": {"3,3": 0.9}})
    for _ in range(3):
        replay = {**TURN, "hint": "POISONED", "smell_grid": {"0,0": 0.9}}
        # Absorbed, not refused (kit SPEC 7.1): a redelivery is the network
        # doing its job and the sender is told it landed. What matters here is
        # unchanged and is asserted below — absorbed means nothing is queued, so
        # the poisoned payload never reaches the game state either way. The old
        # `assert not ...ok` pinned the refusal, which is the behaviour the kit
        # names as turning a retry race into a mutual technical loss.
        assert inboxes.accept("turn", replay).ok

    orchestrator.receive_turn()
    assert orchestrator.state.last_opponent_hint == "by the river", "replay never reached us"
    assert orchestrator.state.opponent_scent.intensity_at((0, 0)) == 0.0


def test_out_of_order_turn_is_refused_with_a_reason() -> None:
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    inboxes.accept("turn", {**TURN, "step": 9})
    result = inboxes.accept("turn", {**TURN, "step": 4})
    assert not result.ok
    assert "stale or replayed" in result.errors[0]
    assert any(event["event"] == "inbox.out_of_order" for event in events)
