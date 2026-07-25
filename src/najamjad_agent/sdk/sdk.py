"""The SDK — the single entry point to everything this agent can do.

Guidelines §4.1 make this mandatory: business logic reaches consumers only
through here, and the GUI, CLI and any future integration hold nothing else.
That is why the dashboard cannot accidentally read a game object and render
something the rules forbid.

The facade deliberately owns no logic of its own. It wires subsystems together
and delegates; if a method here starts making decisions, it belongs in the
domain instead.
"""

from typing import Any

from ..llm.router import LLMRouter
from ..llm.token_meter import TokenMeter
from .queries import (
    assert_local_truth,
    board_view,
    budget_view,
    gatekeeper_view,
    provider_view,
    report_view,
    transcript_view,
    turn_view,
)


class AgentSdk:
    """Everything a consumer may ask of the agent."""

    def __init__(
        self,
        state: Any = None,
        fsm: Any = None,
        router: LLMRouter | None = None,
        meter: TokenMeter | None = None,
        negotiation: Any = None,
        gatekeepers: dict[str, Any] | None = None,
        events: Any = None,
    ) -> None:
        """Hold the subsystems; every one of them is optional before a match."""
        self._state = state
        self._fsm = fsm
        self._router = router
        self._meter = meter
        self._negotiation = negotiation
        self._gatekeepers = gatekeepers or {}
        self._events = events
        self._transcript: list[dict[str, Any]] = []
        self._report: tuple[Any, Any, str] = (None, None, "")

    @property
    def ready(self) -> bool:
        """True once a game is attached and the dashboard has data to show."""
        return self._state is not None

    def attach_game(self, state: Any, fsm: Any) -> None:
        """Bind a freshly started mini-game to the SDK."""
        self._state = state
        self._fsm = fsm
        self._transcript.clear()

    def record_message(self, direction: str, text: str, **fields: Any) -> None:
        """Add one dialogue line, with the provenance the transcript shows."""
        self._transcript.append({"direction": direction, "text": text, **fields})

    def board(self) -> dict[str, Any]:
        """Board, belief heatmap and scent — local truth only."""
        if self._state is None:
            return {"available": False}
        return self._checked({"available": True, **board_view(self._state)})

    def turn(self) -> dict[str, Any]:
        """Turn banner state driven by the game FSM."""
        if self._state is None or self._fsm is None:
            return {"available": False}
        view = turn_view(self._state, self._fsm.phase.value, self._fsm.history)
        return self._checked({"available": True, **view})

    def transcript(self) -> list[dict[str, Any]]:
        """Hints exchanged, each tagged with the model that produced it."""
        return transcript_view(self._transcript)

    def negotiation_timeline(self) -> list[dict[str, Any]]:
        """Every propose/counter/lock step, so nothing is invisible."""
        if self._negotiation is None:
            return []
        return list(getattr(self._negotiation, "timeline", []))

    def budget(self) -> dict[str, Any]:
        """Token spend against the agreed series cap."""
        return budget_view(self._meter)

    def provider(self) -> dict[str, Any]:
        """Which provider is currently answering."""
        return provider_view(self._router)

    def gatekeepers(self) -> list[dict[str, Any]]:
        """Rate-limiter pressure per external service."""
        return gatekeeper_view(self._gatekeepers)

    def record_report(self, reconciliation: Any = None, send: Any = None, error: str = "") -> None:
        """Record what happened to the match report, for the status panel."""
        self._report = (reconciliation, send, error)

    def report(self) -> dict[str, Any]:
        """Reconciliation and email delivery status."""
        return report_view(*self._report)

    def snapshot(self) -> dict[str, Any]:
        """One payload with every panel's data, for the initial page load."""
        return {
            "board": self.board(),
            "turn": self.turn(),
            "transcript": self.transcript(),
            "negotiation": self.negotiation_timeline(),
            "budget": self.budget(),
            "provider": self.provider(),
            "gatekeepers": self.gatekeepers(),
            "report": self.report(),
        }

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """The tail of the event stream that feeds the incident feed."""
        if self._events is None:
            return []
        return list(getattr(self._events, "history", []))[-limit:]

    @staticmethod
    def _checked(payload: dict[str, Any]) -> dict[str, Any]:
        """Enforce the local-truth rule on anything leaving the SDK."""
        assert_local_truth(payload)
        return payload
