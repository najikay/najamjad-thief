"""The WebSocket frame contract.

The dashboard and the server have to agree on what arrives over the socket. In
Assignment 6 that agreement lived only in whichever JavaScript branch happened
to read the field, so a renamed key failed silently in the browser. Here each
frame type is a model, every outbound frame is validated, and an unknown type is
an error rather than a panel that quietly stops updating.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..sdk.queries import assert_local_truth


class _Frame(BaseModel):
    """Shared frame behaviour: extra fields allowed, type always present."""

    model_config = ConfigDict(extra="allow")

    type: str


class SnapshotFrame(_Frame):
    """The whole dashboard state, sent once when a page connects."""

    type: str = "snapshot"
    board: dict[str, Any] = Field(default_factory=dict)
    turn: dict[str, Any] = Field(default_factory=dict)
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    negotiation: list[dict[str, Any]] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    provider: dict[str, Any] = Field(default_factory=dict)
    gatekeepers: list[dict[str, Any]] = Field(default_factory=list)


class EventFrame(_Frame):
    """One event from the bus, pushed the moment it is published."""

    type: str = "event"
    event: str = ""


class BoardFrame(_Frame):
    """Board, barriers, scent and belief heatmap — local truth only."""

    type: str = "board"
    size: int
    own_position: list[int]
    barriers: list[list[int]] = Field(default_factory=list)
    belief: dict[str, float] = Field(default_factory=dict)


class TurnFrame(_Frame):
    """Turn banner: phase, and whether controls accept input."""

    type: str = "turn"
    phase: str
    locked: bool
    step: int = 0


class BudgetFrame(_Frame):
    """Token spend against the negotiated series cap."""

    type: str = "budget"
    series_spent: int = 0
    series_limit: int = 0
    warning: bool = False
    degraded: bool = False


class ProviderFrame(_Frame):
    """Which model is answering right now."""

    type: str = "provider"
    active: str = "template"


class ReportFrame(_Frame):
    """Reconciliation and email delivery status (kills A6 pain #1)."""

    type: str = "report"
    reconciled: bool = False
    agreement: bool | None = None
    message_id: str = ""
    error: str = ""


FRAME_TYPES: dict[str, type[_Frame]] = {
    "snapshot": SnapshotFrame,
    "event": EventFrame,
    "board": BoardFrame,
    "turn": TurnFrame,
    "budget": BudgetFrame,
    "provider": ProviderFrame,
    "report": ReportFrame,
}


def validate_frame(payload: dict[str, Any]) -> dict[str, Any]:
    """Check one outbound frame against its model and the local-truth rule.

    Returns the serialised frame. Raises `ValueError` for an unknown type, so a
    typo becomes a failing test instead of a dead panel.
    """
    kind = payload.get("type")
    model = FRAME_TYPES.get(str(kind))
    if model is None:
        raise ValueError(f"unknown frame type {kind!r}")
    assert_local_truth(payload)
    return model.model_validate(payload).model_dump()
