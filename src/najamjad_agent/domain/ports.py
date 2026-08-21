"""The interfaces the orchestrator conducts — its only view of the outside.

Defining these as protocols (not imports of concrete classes) is what keeps the
orchestrator the single gateway (book rule 3): the turn loop can be exercised
against fakes with no network, no LLM and no clock, which is exactly the seam
Assignment 6 never had a test for.
"""

from typing import Any, Protocol

from ..constants import Move
from .params import Position


class Transport(Protocol):
    """How a peer exchanges turns — implemented by MCP in production."""

    def send_turn(self, message: dict[str, Any]) -> None:
        """Deliver our commit/reveal message to the opponent."""
        ...

    def receive_turn(self, timeout: float) -> dict[str, Any] | None:
        """Await the opponent's message; None on timeout."""
        ...

    def send_audit(self, payload: dict[str, Any]) -> None:
        """Deliver our revealed records at end of mini-game."""
        ...

    def receive_audit(self, timeout: float) -> dict[str, Any] | None:
        """Await the opponent's audit payload; None on timeout."""
        ...

    def reset(self, sub_game: int = 0) -> None:
        """Forget everything carried over from the previous mini-game.

        Part of the protocol rather than an implementation detail, because a
        transport that quietly carries state across mini-games breaks the
        second game of every series — and a fake without this method would hide
        exactly that, which is how the defect survived in the first place.
        """
        ...


class Brain(Protocol):
    """A movement policy. Always deterministic Python (book rule 25)."""

    def pick_move(self, context: "TurnContext") -> Move:
        """Choose a legal move given everything we currently believe."""
        ...

    def pick_barrier(self, context: "TurnContext") -> Position | None:
        """Cop only: choose a barrier cell instead of moving, or None."""
        ...


class Speaker(Protocol):
    """Produces the free-language hint and decides truth vs. lie."""

    def compose(self, context: "TurnContext") -> tuple[str, str]:
        """Return (hint_text, intent) where intent is 'truth' or 'lie'."""
        ...


class Clock(Protocol):
    """Injected time source so deadline behaviour is testable without sleeping."""

    def now(self) -> float:
        """Monotonic seconds."""
        ...


class TurnContext(Protocol):
    """What a brain or speaker may look at when deciding."""

    step: int
    role: str
    own_position: Position
    legal: tuple[Move, ...]
    belief_peak: Position | None
    belief: dict[Position, float]
    scent: dict[Position, float]
    last_hint: str
    barriers_left: int
