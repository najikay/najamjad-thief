"""Wire schemas for MCP messages — tolerant inbound, strict outbound.

The asymmetry is deliberate (ADR-006):

* **Inbound** we accept unknown fields. Every league team writes its own agent;
  refusing a message because it carries an extra key would turn a harmless
  difference into a forfeited match — Assignment 6's costliest failure mode.
  Extras are preserved in `extras` so they can be logged and inspected.
* **Outbound** we validate strictly before anything leaves the process, so a
  malformed message is impossible to send rather than merely unlikely.

Field names mirror the reference implementation exactly; deviating would break
interop with every opponent that started from the lecturer's repo.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TolerantModel(BaseModel):
    """Base for inbound messages: keep unknown keys instead of rejecting them."""

    model_config = ConfigDict(extra="allow")

    @property
    def extras(self) -> dict[str, Any]:
        """Fields the sender included that our schema does not declare."""
        return dict(self.__pydantic_extra__ or {})


class StrictModel(BaseModel):
    """Base for outbound messages: no unknown keys, no silent coercion."""

    model_config = ConfigDict(extra="forbid", strict=False)


class NegotiateTerms(TolerantModel):
    """The proposed game terms carried in a negotiate message."""

    grid_size: int = Field(ge=7)
    max_barriers: int = Field(ge=14)
    max_moves: int = Field(ge=35)
    survival_threshold: int = Field(ge=35)
    num_games: int = Field(default=6, ge=1)
    move_set: list[str] = Field(default_factory=lambda: ["N", "S", "E", "W", "STAY"])


class NegotiateMessage(TolerantModel):
    """Signed proposal exchanged before play (reference `negotiate` tool)."""

    identity: str
    terms: dict[str, Any]
    nonce: str
    signature: str


class TurnMessage(TolerantModel):
    """One turn on the wire (reference `receive_turn` tool).

    `commit` is mandatory — it is the cryptographic anchor of the step. The
    optional fields correspond to actions that only occur on some turns
    (barrier placement, capture claim/response, win claim).
    """

    step: int = Field(ge=0)
    sender: str = ""
    commit: str = Field(min_length=1)
    hint: str = ""
    smell_grid: dict[str, float] = Field(default_factory=dict)
    timestamp: str = ""
    payload: dict[str, Any] | None = None
    barrier_placed: list[int] | None = None
    capture_claim: bool | None = None
    claim_response: bool | None = None
    win_claim: str | None = None

    @model_validator(mode="after")
    def _barrier_is_a_cell(self) -> "TurnMessage":
        """A declared barrier must name exactly one cell (book rules 15-16)."""
        if self.barrier_placed is not None and len(self.barrier_placed) != 2:
            raise ValueError("barrier_placed must be a [row, col] pair")
        return self


class AuditRecord(TolerantModel):
    """One revealed step in an audit payload."""

    payload: dict[str, Any]
    nonce: str = Field(min_length=1)
    commit: str = Field(min_length=1)


class AuditPayload(TolerantModel):
    """End-of-game reveal (reference `submit_audit` tool)."""

    sender: str = ""
    records: list[AuditRecord]
    result_claim: str = ""


class ControlMessage(TolerantModel):
    """Opt-in control channel (reference `receive_control` tool)."""

    kind: str
    status: str = ""
    step_budget: int | None = None

    @model_validator(mode="after")
    def _kind_is_known(self) -> "ControlMessage":
        """Reject control verbs we do not implement rather than guessing."""
        allowed = {"enable", "status", "restart", "quit"}
        if self.kind not in allowed:
            raise ValueError(f"unknown control kind {self.kind!r}; expected one of {sorted(allowed)}")
        return self
