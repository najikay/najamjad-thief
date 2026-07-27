"""The production Transport: our inboxes in, the opponent's server out.

This is the adapter that satisfies `domain.ports.Transport` for real play. The
orchestrator never learns that MCP, HTTP or a tunnel exist — it asks for a turn
and gets one, or does not and resolves cleanly. Keeping that boundary is what
let the whole turn loop be tested without a network in the first place.

Waiting is delegated to the DeadlineTracker so every wait in the system is
bounded by the same configured budget (book rule 6).
"""

from typing import Any

from ..shared.events import Emit
from .deadline import DeadlineTracker
from .inbox import Inboxes
from .mcp_client import PeerClient


class PeerTransport:
    """Bridges the game loop to the peer over MCP."""

    def __init__(
        self,
        inboxes: Inboxes,
        client: PeerClient,
        deadlines: DeadlineTracker,
        emit: Emit | None = None,
    ) -> None:
        """Wire the transport to its inboxes, client and deadline budget."""
        self._inboxes = inboxes
        self._client = client
        self._deadlines = deadlines
        self._emit = emit or (lambda _event: None)

    def send_turn(self, message: dict[str, Any]) -> None:
        """Send one commit or reveal to the opponent."""
        self._client.send("turn", message)

    def receive_turn(self, timeout: float) -> dict[str, Any] | None:
        """Wait for the opponent's next turn within the deadline budget."""
        message = self._deadlines.await_value(
            "opponent-turn",
            lambda remaining: self._inboxes.poll("turn", timeout=max(0.0, remaining)),
            timeout=timeout,
        )
        return self._as_dict(message)

    def send_audit(self, payload: dict[str, Any]) -> None:
        """Best-effort audit delivery — the opponent may already have exited."""
        if not self._client.try_send("audit", payload):
            self._emit({"event": "transport.audit_undelivered"})

    def receive_audit(self, timeout: float) -> dict[str, Any] | None:
        """Wait for the opponent's revealed records."""
        message = self._deadlines.await_value(
            "opponent-audit",
            lambda remaining: self._inboxes.poll("audit", timeout=max(0.0, remaining)),
            timeout=timeout,
        )
        return self._as_dict(message)

    def send_negotiate(self, message: dict[str, Any]) -> None:
        """Deliver our signed terms to the opponent's `negotiate` tool."""
        self._client.send("negotiate", message)

    def reset(self) -> None:
        """Clear per-mini-game state between sub-games.

        Two things have to go, and both bit us in a real two-process series:

        * the **monotonic step guard**, which correctly rejects a replayed turn
          within a game and just as correctly rejected step 1 of game 2 as
          "stale, last accepted was 11" — silently ending our series after one
          mini-game against any opponent;
        * **queued messages** from the finished game, because a turn that
          arrives after a capture belongs to a game that is over and must not
          be read as the opening move of the next one.
        """
        dropped = self._inboxes.drain()
        self._emit({"event": "transport.reset", "dropped": dropped})

    @staticmethod
    def _as_dict(message: Any) -> dict[str, Any] | None:
        """Hand the domain plain dicts, never pydantic models."""
        if message is None:
            return None
        if hasattr(message, "model_dump"):
            return message.model_dump(mode="json", exclude_none=True)
        return dict(message)
