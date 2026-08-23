"""Re-delivering our newest turn after a silent wait (kit §7.1, client half).

An acknowledged push is not a consumed one: a peer whose per-window process
died after answering takes the message to its grave, and a client that trusts
that ack waits forever on a corpse's promise — three counted attempts against
anrbj666, one signature. At-least-once makes the retry free: receivers absorb
duplicates by commit, ours and every peer's alike, so the sender who fails to
retry is the nonconformant one. Split from `orchestrator` for the file budget.
"""

from __future__ import annotations

from typing import Any


def repush_last_turn(orchestrator: Any) -> None:
    """Best-effort redelivery; the wait loop owns recovery, not this send."""
    last = getattr(orchestrator, "_last_turn", None)
    if last is None:
        return
    try:
        orchestrator._transport.send_turn(last)
        orchestrator.event("turn.repushed", step=orchestrator.state.step)
    except Exception:  # noqa: BLE001 - a briefly unreachable door is the next wait's problem
        orchestrator.event("turn.repush_failed", step=orchestrator.state.step)


def send_and_retain(orchestrator: Any, message: Any) -> None:
    """Send a turn and remember it as the redelivery candidate."""
    orchestrator._transport.send_turn(message)
    orchestrator._last_turn = message
