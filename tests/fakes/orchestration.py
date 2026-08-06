"""Fakes and builders shared by orchestrator and series tests.

Deliberately hand-written rather than Mock-based: these fakes encode what a
*correct* peer does, so a test that passes against them is evidence about the
protocol, not about our mocking.
"""

from typing import Any

from najamjad_agent.constants import Move, Phase, Role
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.fsm import GameStateMachine
from najamjad_agent.domain.game_state import GameState, TurnFacts
from najamjad_agent.domain.ledger import CommitLedger
from najamjad_agent.domain.orchestrator import Orchestrator
from najamjad_agent.domain.params import GameParams, Position
from najamjad_agent.domain.scent import ScentField

CONFIG: dict = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}


class FakeTransport:
    """Records what we sent and replays a scripted opponent."""

    def __init__(self, inbox: list[dict[str, Any]] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.audits: list[dict[str, Any]] = []
        self.inbox: list[dict[str, Any]] = list(inbox or [])
        self.timeouts = 0

    def send_turn(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def receive_turn(self, timeout: float) -> dict[str, Any] | None:
        if not self.inbox:
            self.timeouts += 1
            return None
        return self.inbox.pop(0)

    def send_audit(self, payload: dict[str, Any]) -> None:
        self.audits.append(payload)

    def receive_audit(self, timeout: float) -> dict[str, Any] | None:
        return None


class ScriptedBrain:
    """Plays a fixed move sequence; optionally proposes barriers."""

    def __init__(self, moves: list[Move], barriers: list[Position] | None = None) -> None:
        self.moves = list(moves)
        self.barriers = list(barriers or [])
        self.seen: list[TurnFacts] = []

    def pick_move(self, context: TurnFacts) -> Move:
        self.seen.append(context)
        return self.moves.pop(0) if self.moves else Move.STAY

    def pick_barrier(self, context: TurnFacts) -> Position | None:
        return self.barriers.pop(0) if self.barriers else None


class FixedSpeaker:
    """A deterministic speaker so hint text never destabilises a test."""

    def __init__(self, text: str = "somewhere in the city", intent: str = "truth") -> None:
        self.text = text
        self.intent = intent

    def compose(self, context: TurnFacts) -> tuple[str, str]:
        return self.text, self.intent


class FakeClock:
    """Monotonic clock the test drives by hand."""

    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        self.value += 1.0
        return self.value


def build_state(
    role: Role,
    position: Position | None = None,
    board: Board | None = None,
    emission: Any = None,
) -> GameState:
    """A fresh mini-game state for one peer."""
    params = GameParams.from_config(CONFIG)
    grid = board or Board(params)
    start = position or (params.cop_start if role is Role.COP else params.thief_start)
    return GameState(
        board=grid,
        role=role,
        sub_game=1,
        own_position=start,
        belief=BeliefGrid(grid),
        own_scent=ScentField(board_size=grid.size),
        opponent_scent=ScentField(board_size=grid.size),
        ledger=CommitLedger(sub_game=1),
        **({"emission": emission} if emission is not None else {}),
    )


def build_orchestrator(
    role: Role = Role.COP,
    moves: list[Move] | None = None,
    barriers: list[Position] | None = None,
    inbox: list[dict[str, Any]] | None = None,
    events: list[dict] | None = None,
    **kwargs: Any,
) -> tuple[Orchestrator, FakeTransport, ScriptedBrain]:
    """Assemble an orchestrator wired entirely to fakes."""
    state = build_state(
        role,
        position=kwargs.pop("position", None),
        board=kwargs.pop("board", None),
        emission=kwargs.pop("emission", None),
    )
    transport = FakeTransport(inbox)
    brain = ScriptedBrain(moves or [], barriers)
    sink = events.append if events is not None else None
    fsm = GameStateMachine(game_uid="test-uid", on_transition=sink)
    fsm.to(Phase.WAITING_FOR_OPPONENT)  # negotiation is complete before play starts
    orchestrator = Orchestrator(
        state=state,
        fsm=fsm,
        transport=transport,
        brain=brain,
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        emit=sink,
        **kwargs,
    )
    return orchestrator, transport, brain
