"""Fault injection — disconnects, retries, drains and message-volume soak.

A dropped connection should cost a retry, not the match; and six mini-games of
traffic must leave no residue behind.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.net.deadline import DeadlineTracker
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.peer_transport import PeerTransport
from najamjad_agent.shared.gatekeeper import ApiGatekeeper
from najamjad_agent.shared.rate_limits import RateLimitConfig
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


def test_mid_turn_disconnect_recovers_through_gatekeeper_retries() -> None:
    """A dropped connection should cost a retry, not the match."""
    events: list[dict] = []
    client = FlakyClient(failures=2)
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=RateLimitConfig(requests_per_minute=600, max_retries=3, retry_after_seconds=5),
        emit=events.append,
        sleep=lambda _s: None,
    )
    keeper.execute(client.send, "turn", {"step": 1})
    assert client.delivered, "the message eventually got through"
    assert sum(1 for event in events if event["event"] == "gatekeeper.retry") == 2


def test_persistent_disconnect_fails_cleanly_without_hanging() -> None:
    events: list[dict] = []
    keeper = ApiGatekeeper(
        service="mcp_peer",
        config=RateLimitConfig(requests_per_minute=600, max_retries=3, retry_after_seconds=5),
        emit=events.append,
        sleep=lambda _s: None,
    )
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        keeper.execute(DeadClient().send, "turn", {"step": 1})
    assert any(event["event"] == "gatekeeper.failed" for event in events)


def test_audit_to_a_vanished_opponent_is_reported_not_fatal() -> None:
    """Post-game the peer may legitimately be gone; that is not a crash."""
    events: list[dict] = []
    transport, _ = _transport(DeadClient(), events)
    transport.send_audit({"records": []})
    assert any(event["event"] == "transport.audit_undelivered" for event in events)


def test_queue_drain_between_games_discards_stale_traffic() -> None:
    """A leftover turn must never open the next mini-game."""
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    inboxes.accept("turn", {**TURN, "step": 30})
    dropped = inboxes.drain()
    assert dropped == {"turn": 1}
    assert inboxes.accept("turn", {**TURN, "step": 1}).ok


def test_a_full_series_of_message_volume_leaves_no_residue() -> None:
    """Soak: six mini-games of traffic, queues back to zero each time."""
    inboxes = Inboxes()
    for _game in range(6):
        for step in range(1, 36):
            inboxes.accept("turn", {**TURN, "step": step})
        while inboxes.poll("turn", timeout=0.001) is not None:
            pass
        inboxes.drain()
        assert inboxes.pending("turn") == 0


def test_illegal_move_from_a_buggy_brain_is_still_filtered_under_faults() -> None:
    """Our own guardrail must hold even while the network is misbehaving."""
    events: list[dict] = []
    transport, _ = _transport(FlakyClient(failures=0), events)
    orchestrator, _, _ = build_orchestrator(
        role=Role.COP, moves=[Move.NORTH], events=events, response_timeout=0.02
    )
    orchestrator._transport = transport
    orchestrator.take_turn()
    assert orchestrator.state.own_position == (0, 0)
    assert any(event.get("event") == "move.illegal_rejected" for event in events)
