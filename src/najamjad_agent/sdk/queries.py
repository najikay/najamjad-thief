"""Read models for the dashboard — and the boundary that keeps it honest.

Book rules 8-9 forbid showing the objective board: a live UI may display only
what this agent legitimately knows, and a violation is disqualification for an
illegal information advantage. Since the protocol fix, we genuinely do not know
the opponent's position — but "we could not leak it anyway" is a weaker
guarantee than "the read model has no field for it", so this is where the rule
is enforced.

Every panel gets a plain dictionary built here. The UI never touches game
objects, so it cannot reach past what these functions choose to expose.
"""

from typing import Any

from ..constants import Phase
from ..domain.game_state import GameState

# Fields a view model may never carry, whatever a future caller passes.
FORBIDDEN_KEYS = frozenset(
    {"opponent_position", "their_position", "true_position", "nonce", "nonces"}
)


def board_view(state: GameState) -> dict[str, Any]:
    """The board as we may legitimately draw it (FR-UI-1)."""
    return {
        "size": state.board.size,
        "own_position": list(state.own_position),
        "barriers": sorted([row, col] for row, col in state.board.barriers),
        "belief": {f"{row},{col}": round(value, 5) for (row, col), value in state.belief.as_dict().items()},
        "belief_peak": list(state.belief.peak() or ()),
        "opponent_scent": state.opponent_scent.snapshot(),
        "role": state.role.value,
        "step": state.step,
        "barriers_left": state.barriers_left,
    }


def turn_view(state: GameState, phase: str, history: list[Any] | None = None) -> dict[str, Any]:
    """Turn banner state: whose move it is, and whether input is accepted.

    Only COMPUTING_MOVE is ours to act in. Every other phase is either the
    opponent's or a protocol step the FSM owns, and offering a control there
    would let a click race the state machine — the A6 lesson behind T-1820.
    """
    return {
        "phase": phase,
        "locked": phase != Phase.COMPUTING_MOVE.value,
        "step": state.step,
        "full_turns": state.full_turns,
        "sub_game": state.sub_game,
        "recent_phases": [str(getattr(entry, "value", entry)) for entry in (history or [])[-8:]],
    }


def transcript_view(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dialogue with per-message provenance (FR-LLM-2)."""
    return [
        {
            "direction": message.get("direction", "in"),
            "text": message.get("text", ""),
            "intent": message.get("intent", ""),
            "provider": message.get("provider", ""),
            "model": message.get("model", ""),
            "step": message.get("step", 0),
        }
        for message in messages
    ]


def budget_view(meter: Any) -> dict[str, Any]:
    """Token usage against the agreed cap, with its warning states."""
    if meter is None:
        return {"available": False}
    report = meter.report()
    return {
        "available": True,
        "series_spent": report["series_total"],
        "series_limit": report["series_limit"],
        "ratio": round(meter.series.ratio, 4),
        "warning": meter.series.ratio >= 0.70,
        "degraded": meter.series.should_degrade,
        "by_purpose": report["by_purpose"],
    }


def provider_view(router: Any) -> dict[str, Any]:
    """Which model is speaking right now — the badge (FR-LLM-2)."""
    if router is None:
        return {"available": False, "active": "template"}
    return {"available": True, "active": router.active, "providers": router.status()}


def gatekeeper_view(gatekeepers: dict[str, Any]) -> list[dict[str, Any]]:
    """Queue depth and retry pressure per external service (ADR-009)."""
    views = []
    for name, keeper in sorted(gatekeepers.items()):
        status = keeper.status()
        views.append(
            {
                "service": name,
                "waiting": status.waiting,
                "in_flight": status.in_flight,
                "calls_made": status.calls_made,
            }
        )
    return views


def report_view(reconciliation: Any, send: Any, error: str = "") -> dict[str, Any]:
    """Reconciliation and delivery status of the match report (FR-REP-3).

    A6's worst failure was an email that silently did not go out when we were
    not the initiating side, discovered only after the deadline. This panel
    exists so that state is on screen rather than in a log nobody opened:
    `agreement` is `None` only while genuinely undecided, never as a stand-in
    for "we forgot to reconcile" (A6 pain #5).
    """
    view: dict[str, Any] = {
        "reconciled": reconciliation is not None,
        "status": getattr(reconciliation, "status", "pending"),
        "agreement": reconciliation.confirmed if reconciliation is not None else None,
        "differences": list(getattr(reconciliation, "differences", [])),
        "sent": bool(send is not None and send.delivered),
        "message_id": getattr(send, "message_id", ""),
        "error": error,
    }
    view["needs_attention"] = bool(error) or (view["reconciled"] and not view["sent"])
    return view


def assert_local_truth(payload: Any) -> None:
    """Raise if a view model carries something the UI may not display.

    Applied to every outbound frame. Cheap, and it turns a disqualification
    risk into a failing test rather than a discovery during grading.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_KEYS:
                raise ValueError(f"view model may not expose {key!r} (book rules 8-9)")
            assert_local_truth(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_local_truth(item)
