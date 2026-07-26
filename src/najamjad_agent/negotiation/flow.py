"""The negotiation state machine — and the record of what was said.

Assignment 6's negotiating agent existed only in documentation: nobody could
tell whether it had run, because nothing was persisted. Here every proposal,
counter, refusal and lock is appended to a timeline that the dashboard renders
and the match workspace keeps. If someone asks "did we negotiate?", the answer
is a file, not a shrug.

Illegal transitions raise rather than drift, for the same reason as the game
FSM: a negotiation that silently skips verification would sign a contract we
never actually checked.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..shared.events import Emit
from .contract import Contract, ContractError
from .playbook import COUNTER, REJECT, Playbook


class Stage(str, Enum):
    """Where a negotiation has got to."""

    IDLE = "idle"
    PROPOSED = "proposed"
    COUNTERED = "countered"
    AGREED = "agreed"
    LOCKED = "locked"
    ABANDONED = "abandoned"


ALLOWED: dict[Stage, frozenset[Stage]] = {
    Stage.IDLE: frozenset({Stage.PROPOSED, Stage.COUNTERED, Stage.ABANDONED}),
    Stage.PROPOSED: frozenset({Stage.COUNTERED, Stage.AGREED, Stage.ABANDONED}),
    Stage.COUNTERED: frozenset({Stage.PROPOSED, Stage.COUNTERED, Stage.AGREED, Stage.ABANDONED}),
    Stage.AGREED: frozenset({Stage.LOCKED, Stage.ABANDONED}),
    Stage.LOCKED: frozenset(),
    Stage.ABANDONED: frozenset(),
}


class NegotiationError(Exception):
    """Raised on an illegal negotiation transition."""


@dataclass
class Negotiation:
    """Drives one negotiation and records every step of it."""

    playbook: Playbook = field(default_factory=Playbook)
    our_group: str = ""
    emit: Emit | None = None
    stage: Stage = Stage.IDLE
    timeline: list[dict[str, Any]] = field(default_factory=list)
    contract: Contract | None = None
    their_group: str = ""

    @property
    def locked(self) -> bool:
        """True once terms are agreed, verified and frozen."""
        return self.stage is Stage.LOCKED

    def _to(self, stage: Stage) -> None:
        """Move the negotiation forward, refusing anything off the graph."""
        if stage not in ALLOWED[self.stage]:
            raise NegotiationError(f"illegal negotiation step {self.stage.value} -> {stage.value}")
        self.stage = stage

    def _record(self, action: str, **fields: Any) -> dict[str, Any]:
        """Append one visible step to the timeline."""
        entry = {"action": action, "stage": self.stage.value, **fields}
        self.timeline.append(entry)
        if self.emit is not None:
            self.emit({"event": f"negotiation.{action}", **fields})
        return entry

    def propose(self, terms: dict[str, Any] | None = None) -> dict[str, Any]:
        """Open with our preferred position (or a supplied set of terms)."""
        offer = terms if terms is not None else self.playbook.opening_terms()
        self._to(Stage.PROPOSED)
        self._record("proposed", terms=offer)
        return offer

    def receive(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the opponent's proposal against the playbook."""
        assessment = self.playbook.evaluate(proposal)
        verdict = assessment["verdict"]
        if verdict == REJECT:
            self._to(Stage.ABANDONED)
            self._record("rejected", reasons=assessment["reasons"], terms=proposal)
        elif verdict == COUNTER:
            self._to(Stage.COUNTERED)
            self._record("countered", counter=assessment["counter"], reasons=assessment["reasons"])
        else:
            self._to(Stage.AGREED)
            self._record("accepted", terms=proposal)
        return assessment

    def agree(self, terms: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build and sign our side of the agreed terms."""
        if self.stage not in (Stage.PROPOSED, Stage.COUNTERED, Stage.AGREED):
            raise NegotiationError(f"cannot agree from stage {self.stage.value}")
        self.contract = Contract(terms, identity=identity)
        if self.stage is not Stage.AGREED:
            self._to(Stage.AGREED)
        message = self.contract.signed()
        self._record("signed", sha256=self.contract.sha256)
        return message

    def lock(self, peer_message: dict[str, Any], their_group: str) -> dict[str, Any]:
        """Verify the peer's signature and freeze the contract."""
        if self.contract is None:
            raise NegotiationError("cannot lock before agreeing terms")
        try:
            self.contract.verify_peer(peer_message)
        except ContractError as error:
            self._to(Stage.ABANDONED)
            self._record("refused", reason=str(error))
            raise
        self.their_group = their_group
        game_id, game_uid = self.contract.game_ids(self.our_group, their_group)
        self._to(Stage.LOCKED)
        return self._record(
            "locked", game_id=game_id, game_uid=game_uid, sha256=self.contract.sha256
        )

    def abandon(self, reason: str) -> dict[str, Any]:
        """Walk away cleanly — no contract, nothing half-signed."""
        self._to(Stage.ABANDONED)
        return self._record("abandoned", reason=reason)
