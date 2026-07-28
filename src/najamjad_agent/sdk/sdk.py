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
from .actions import AgentActions
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


def _emitter(events: Any) -> Any:
    """Publish onto the bus when there is one that can publish.

    A read-only event source (one that only exposes `history`) is a legitimate
    thing to hand the SDK; requiring `publish` would make the facade refuse it
    for the sake of a side effect nobody asked for.
    """
    return getattr(events, "publish", None) or (lambda _event: None)


class AgentSdk:
    """Everything a consumer may ask of the agent.

    Reads are methods here; writes live on `.actions`. Both halves are pure
    delegation, and together they are the whole surface a UI or CLI may touch.
    """

    def __init__(
        self,
        state: Any = None,
        fsm: Any = None,
        router: LLMRouter | None = None,
        meter: TokenMeter | None = None,
        negotiation: Any = None,
        gatekeepers: dict[str, Any] | None = None,
        events: Any = None,
        actions: AgentActions | None = None,
        controls_enabled: bool = False,
        practice: Any = None,
    ) -> None:
        """Hold the subsystems; every one of them is optional before a match."""
        self.actions = actions or AgentActions(negotiation=negotiation, emit=_emitter(events))
        self._state = state
        self._fsm = fsm
        self._router = router
        self._meter = meter
        self._negotiation = negotiation
        self._gatekeepers = gatekeepers or {}
        self._events = events
        self._controls_enabled = controls_enabled
        self._practice = practice
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

    @property
    def controls_enabled(self) -> bool:
        """Whether the dashboard may take write actions.

        Lives here rather than in the UI because the UI package may reach the
        agent only through this facade (ADR-005) — including for a feature flag.
        """
        return bool(self._controls_enabled)

    def practice(self) -> dict[str, Any]:
        """Whether this run can reach the lecturer, and where its mail goes.

        Surfaced beside the readiness checks rather than buried in settings: the
        cost of a wrong answer is asymmetric. Believing a counted match is
        practice sends the graded report to the wrong inbox; believing practice
        is counted is merely an unnecessary flinch.
        """
        from ..shared.practice import current

        mode = self._practice if self._practice is not None else current()
        return dict(mode.state())

    def set_practice(self, enabled: bool) -> dict[str, Any]:
        """Turn practice mode on or off, and report what is now in force.

        Returns the mode read back after writing rather than the value asked
        for: a toggle that echoed its input would keep saying "on" even if the
        write failed, which is the one lie this switch must not tell.
        """
        from ..shared.practice import save_practice

        return dict(save_practice(bool(enabled)).state())

    def liveness(self, timeout: float = 1.0) -> dict[str, Any]:
        """Which of our three endpoints are answering right now.

        A green light means something accepted a TCP connection — not that the
        protocol works. `net/liveness.py` says why it claims no more than that.
        """
        from ..net.liveness import blocking_issues, survey

        probes = survey(
            {
                "our agent": getattr(self.actions, "public_url", ""),
                "opponent": getattr(self.actions, "opponent_url", ""),
            },
            timeout=timeout,
        )
        return {"probes": probes, "blocking": blocking_issues(probes)}

    def cockpit(self) -> dict[str, Any]:
        """Match-day readiness in one payload (T-1819).

        Answers the only question that matters five minutes before a match:
        *can we play right now, and if not, what is red*. The preflight checks
        are the same ones the CLI runs, so the cockpit cannot say ready while
        `preflight` says otherwise.
        """
        report = None
        try:
            report = self.actions.preflight()
        except Exception:  # noqa: BLE001 - an unconfigured agent is not an error here
            report = None
        return {
            "ready": self.ready,
            "public_url": getattr(self.actions, "public_url", ""),
            "checks": [
                {"name": check.name, "passed": check.passed, "detail": check.detail}
                for check in (getattr(report, "checks", None) or [])
            ],
            "exit_code": getattr(report, "exit_code", None),
            "provider": self.provider(),
            "budget": self.budget(),
            "artifacts": dict(getattr(self.actions, "last_artifacts", {}) or {}),
            "practice": self.practice(),
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
