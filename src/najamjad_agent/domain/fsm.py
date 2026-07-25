"""The game state machine — illegal transitions raise rather than drift.

Book rules 4-5 make this mandatory, and the reason is practical: with no
referee, a peer that lets its state drift ends up committing when it should be
verifying, deadlocks, and loses technically. Encoding the legal graph once and
refusing everything else turns a whole class of protocol bugs into a loud,
immediate exception at the exact step where it happened.

Every accepted transition emits an event carrying `game_uid` and `step`, so the
dashboard and the post-match analysis see the same history the FSM saw.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from ..constants import Phase

# The legal graph (PLAN §2.1). Error transitions into TECHNICAL_LOSS are
# deliberately narrow: only the phases that wait on the network can time out.
#
# Two paths beyond the book's headline cycle are declared because the real
# protocol needs them: a peer sitting in WAITING_FOR_OPPONENT verifies the
# message that arrives (it does not compute first), and our own move can end
# the mini-game outright — a barrier capture — while we are AWAITING_REVEAL.
TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.NEGOTIATING: frozenset({Phase.WAITING_FOR_OPPONENT, Phase.TECHNICAL_LOSS}),
    Phase.WAITING_FOR_OPPONENT: frozenset(
        {Phase.COMPUTING_MOVE, Phase.VERIFYING, Phase.GAME_END, Phase.TECHNICAL_LOSS}
    ),
    Phase.COMPUTING_MOVE: frozenset({Phase.COMMITTING, Phase.TECHNICAL_LOSS}),
    Phase.COMMITTING: frozenset({Phase.AWAITING_REVEAL, Phase.TECHNICAL_LOSS}),
    Phase.AWAITING_REVEAL: frozenset(
        {Phase.VERIFYING, Phase.GAME_END, Phase.TECHNICAL_LOSS}
    ),
    Phase.VERIFYING: frozenset(
        {Phase.WAITING_FOR_OPPONENT, Phase.GAME_END, Phase.TECHNICAL_LOSS}
    ),
    Phase.GAME_END: frozenset({Phase.AUDITING, Phase.REPORTING, Phase.TECHNICAL_LOSS}),
    Phase.AUDITING: frozenset({Phase.REPORTING, Phase.TECHNICAL_LOSS}),
    Phase.REPORTING: frozenset(),
    Phase.TECHNICAL_LOSS: frozenset({Phase.REPORTING}),
}
TERMINAL = frozenset({Phase.REPORTING})


class IllegalTransitionError(Exception):
    """Raised the moment the game tries to enter a state it may not."""

    def __init__(self, source: Phase, target: Phase) -> None:
        """Name both ends so the log points straight at the offending call."""
        super().__init__(f"illegal transition {source.value} -> {target.value}")
        self.source = source
        self.target = target


@dataclass
class GameStateMachine:
    """Tracks the current phase and refuses anything off the legal graph."""

    game_uid: str = ""
    phase: Phase = Phase.NEGOTIATING
    step: int = 0
    on_transition: Callable[[dict], None] | None = None
    history: list[Phase] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Seed the history with the starting phase."""
        self.history.append(self.phase)

    @property
    def is_terminal(self) -> bool:
        """True once the mini-game can make no further transition."""
        return self.phase in TERMINAL

    def can(self, target: Phase) -> bool:
        """Whether `target` is reachable from the current phase."""
        return target in TRANSITIONS[self.phase]

    def to(self, target: Phase, step: int | None = None) -> Phase:
        """Move to `target`, raising when the transition is not legal."""
        if not self.can(target):
            raise IllegalTransitionError(self.phase, target)
        source = self.phase
        self.phase = target
        if step is not None:
            self.step = step
        self.history.append(target)
        self._emit(source, target)
        return target

    def fail(self, reason: str) -> Phase:
        """Enter TECHNICAL_LOSS from any phase that allows it."""
        target = Phase.TECHNICAL_LOSS
        if not self.can(target):
            raise IllegalTransitionError(self.phase, target)
        source = self.phase
        self.phase = target
        self.history.append(target)
        self._emit(source, target, reason=reason)
        return target

    def _emit(self, source: Phase, target: Phase, reason: str = "") -> None:
        """Publish the transition for logs, the dashboard, and later analysis."""
        if self.on_transition is None:
            return
        event = {
            "event": "fsm.transition",
            "game_uid": self.game_uid,
            "step": self.step,
            "from": source.value,
            "to": target.value,
        }
        if reason:
            event["reason"] = reason
        self.on_transition(event)
