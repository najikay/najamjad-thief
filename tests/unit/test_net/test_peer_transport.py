"""Tests for the production transport adapter (inboxes ↔ opponent client)."""

import pytest

from najamjad_agent.net.deadline import DeadlineTracker
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.peer_transport import PeerTransport

TURN = {"step": 1, "sender": "rival", "commit": "a" * 64, "hint": "north side"}


class RecordingClient:
    """Stands in for the MCP client, recording what would be sent."""

    def __init__(self, fail_kinds: set[str] | None = None) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.fail_kinds = fail_kinds or set()

    def send(self, kind: str, payload: dict) -> None:
        if kind in self.fail_kinds:
            raise RuntimeError("peer unreachable")
        self.sent.append((kind, payload))

    def try_send(self, kind: str, payload: dict) -> bool:
        try:
            self.send(kind, payload)
        except RuntimeError:
            return False
        return True


@pytest.fixture()
def parts() -> tuple[PeerTransport, Inboxes, RecordingClient, list[dict]]:
    events: list[dict] = []
    inboxes = Inboxes(emit=events.append)
    client = RecordingClient()
    tracker = DeadlineTracker(response_timeout=0.05, max_retries=2, emit=events.append)
    transport = PeerTransport(inboxes, client, tracker, emit=events.append)
    return transport, inboxes, client, events


def test_sending_a_turn_reaches_the_client(parts) -> None:
    transport, _, client, _ = parts
    transport.send_turn({"step": 1, "commit": "c"})
    assert client.sent == [("turn", {"step": 1, "commit": "c"})]


def test_receiving_a_turn_returns_a_plain_dict(parts) -> None:
    """The domain must never be handed a pydantic model."""
    transport, inboxes, _, _ = parts
    inboxes.accept("turn", TURN)
    message = transport.receive_turn(timeout=0.05)
    assert isinstance(message, dict)
    assert message["commit"] == TURN["commit"]
    assert message["step"] == 1


def test_receive_returns_none_when_the_peer_is_silent(parts) -> None:
    """Bounded wait: silence resolves, it does not hang."""
    transport, _, _, events = parts
    assert transport.receive_turn(timeout=0.02) is None
    assert any(event["event"] == "deadline.timeout" for event in events)


def test_optional_fields_are_omitted_not_null(parts) -> None:
    """Nulls on the wire are how A6's report became unreadable."""
    transport, inboxes, _, _ = parts
    inboxes.accept("turn", TURN)
    message = transport.receive_turn(timeout=0.05)
    assert "barrier_placed" not in message
    assert "capture_claim" not in message


def test_audit_send_is_best_effort_and_reported(parts) -> None:
    transport, _, client, events = parts
    client.fail_kinds.add("audit")
    transport.send_audit({"records": []})
    assert any(event["event"] == "transport.audit_undelivered" for event in events)


def test_successful_audit_send_is_quiet(parts) -> None:
    transport, _, client, events = parts
    transport.send_audit({"records": []})
    assert client.sent[0][0] == "audit"
    assert not any(event["event"] == "transport.audit_undelivered" for event in events)


def test_receiving_an_audit_uses_the_deadline_budget(parts) -> None:
    transport, inboxes, _, _ = parts
    inboxes.accept("audit", {"records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c"}]})
    payload = transport.receive_audit(timeout=0.05)
    assert payload is not None
    assert payload["records"][0]["nonce"] == "n"


def test_missing_audit_resolves_to_none(parts) -> None:
    transport, _, _, _ = parts
    assert transport.receive_audit(timeout=0.02) is None


def test_a_plain_dict_message_passes_through_unchanged(parts) -> None:
    """Defensive: a fake or future transport may hand us a raw dict."""
    transport, _, _, _ = parts
    assert transport._as_dict({"step": 2}) == {"step": 2}
    assert transport._as_dict(None) is None
