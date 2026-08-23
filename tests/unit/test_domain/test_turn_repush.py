"""The client half of kit §7.1: a silent wait re-delivers our newest turn.

An acknowledged push is not a consumed one. anrbj666's per-window servers
answered our step-1 turn and died before their runner read it — three counted
attempts, one signature — and our client trusted the ack and waited on a
corpse's promise. At-least-once cuts both ways: receivers absorb duplicates,
so the sender who fails to retry is the nonconformant one.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.domain.orchestrator import Orchestrator


class _Transport:
    """Counts sends; never delivers an opponent turn."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.fail_sends = False

    def receive_turn(self, timeout: float) -> None:
        return None

    def send_turn(self, message: Any) -> None:
        if self.fail_sends:
            raise ConnectionError("door down")
        self.sent.append(message)


def _orchestrator(transport: _Transport) -> Orchestrator:
    orc = Orchestrator.__new__(Orchestrator)
    orc._transport = transport
    orc._timeout = 0.0
    orc._max_retries = 3
    orc.state = type("S", (), {"step": 5})()
    orc.events = []
    orc.event = lambda name, **fields: orc.events.append((name, fields))
    return orc


def test_a_silent_wait_repushes_the_last_turn() -> None:
    transport = _Transport()
    orc = _orchestrator(transport)
    orc._last_turn = {"step": 5, "commit": "abc"}

    assert orc._await_turn() is None

    assert len(transport.sent) == 3, "every timed-out round must re-deliver"
    assert all(m == {"step": 5, "commit": "abc"} for m in transport.sent)
    assert ("turn.repushed", {"step": 5}) in orc.events


def test_no_turn_sent_yet_means_nothing_to_repush() -> None:
    """The responder side has no turn of its own while awaiting an opener."""
    transport = _Transport()
    orc = _orchestrator(transport)
    orc.state.step = 0
    orc.OPENER_PATIENCE = 2

    assert orc._await_turn() is None

    assert transport.sent == []


def test_a_failed_repush_does_not_break_the_wait() -> None:
    """Best-effort: an unreachable door is the next wait's problem."""
    transport = _Transport()
    transport.fail_sends = True
    orc = _orchestrator(transport)
    orc._last_turn = {"step": 5}

    assert orc._await_turn() is None

    assert ("turn.repush_failed", {"step": 5}) in orc.events
