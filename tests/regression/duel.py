"""Run our brain against a scripted opponent and count the steps it survived.

The measuring instrument for every strategy change. Deliberately offline and
deterministic: no network, no LLM, no orchestrator — a brain, a board, and an
opponent that plays a fixed line.

**The thief is given the cop's exact cell.** That is not realism, it is
diagnosis: it separates "our move policy is wrong" from "our belief about where
the cop is was wrong". A thief that loses to a sweep *while being told exactly
where the sweeper is* has a policy problem, and no amount of better sensing
fixes it. `run_duel(perfect_information=False)` re-runs the same line through
whatever belief the caller supplies, for when the question is the other one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.capture import is_immobilised
from najamjad_agent.domain.params import GameParams, Position
from najamjad_agent.domain.scent import ScentField

#: `(cop cell, step, thief cell) -> belief`. The thief cell is passed because a
#: real belief excludes our own square, and a model that cannot see where we
#: stand cannot reproduce what the orchestrator actually computes.
BeliefFor = Callable[[Position, int, Position], dict[Position, float]]


@dataclass(frozen=True)
class DuelResult:
    """What one replayed mini-game did."""

    steps_survived: int
    captured: bool
    path: tuple[Position, ...]
    reason: str

    @property
    def survived(self) -> bool:
        """True when the thief outlasted the agreed step budget."""
        return not self.captured


class Facts:
    """The read-only view a brain is given, matching the orchestrator's."""

    def __init__(
        self,
        board: Board,
        position: Position,
        belief: dict[Position, float],
        step: int,
        left: int,
        own_scent: dict[Position, float] | None = None,
    ) -> None:
        self.board = board
        self.own_position = position
        self.belief = belief
        self.scent: dict[Position, float] = {}
        #: Our own trail. It was omitted, and omitting it hid the freeze: the
        #: only term in the fallback policy that penalises re-treading ground
        #: is this one, so a harness that always passed `{}` was measuring a
        #: thief with no memory of where it had been.
        self.own_scent: dict[Position, float] = own_scent or {}
        self.legal = tuple(Move)
        self.barriers_left = 0
        self.role = "thief"
        self.step = step
        self.steps_remaining = left
        self.sub_game = 1


def _certain(cell: Position) -> dict[Position, float]:
    """A belief that knows exactly where the cop is."""
    return {cell: 1.0}


def run_duel(
    brain: Any,
    cop_line: Sequence[Position],
    params: GameParams,
    barriers: Sequence[Position] = (),
    belief_for: BeliefFor | None = None,
) -> DuelResult:
    """Replay `cop_line` against `brain` and report how long the thief lasted.

    Input: a thief brain, the cop's cells in order, the agreed params, the cop's
    barriers **in the order it placed them, one per step**, and optionally a
    belief model (default: perfect information).
    Output: a `DuelResult`.
    Setup: none — no network, no clock, no randomness beyond the brain's own.

    Barriers arrive on a schedule rather than all at once, and that is not a
    detail. Placed up front they are a static maze the thief routes around;
    placed one per step behind a sweeping cop they progressively delete the
    board the thief was counting on. The first version of this harness seeded
    them all at step 0 and reported a comfortable 35/35 survival against a line
    that beat us three times out of three — a gate that green-lights everything
    is worse than no gate.

    Each step runs cop-moves, cop-walls, thief-moves, which is the order the
    event log shows: the barrier at step N lands on a cell the cop occupied
    before step N.

    The cop repeats its final cell once the scripted line runs out, so a short
    line does not silently hand the thief a win it never earned.
    """
    board = Board(params)
    thief: Position = params.thief_start
    path: list[Position] = [thief]
    horizon = min(params.survival_threshold, params.max_moves)
    belief = belief_for or (lambda cell, _step, _thief: _certain(cell))
    # The real thief cannot help emitting this, and the policy reads it to
    # avoid re-treading its own ground. A real field rather than a stub: the
    # decay rate and the ceiling are what decide whether staying put is
    # actually punished, and inventing softer ones here would flatter us.
    trail = ScentField(params.grid_size)
    trail.deposit(thief)

    for step in range(1, horizon + 1):
        cop = tuple(cop_line[min(step - 1, len(cop_line) - 1)])
        if cop == thief:
            return DuelResult(step - 1, True, tuple(path), "claim")
        if step <= len(barriers):
            wall = tuple(barriers[step - 1])
            if wall == thief:
                return DuelResult(step - 1, True, tuple(path), "walled in place")
            board = board.with_barrier(wall)
        if is_immobilised(board, thief):
            return DuelResult(step - 1, True, tuple(path), "immobilised")

        own = {cell: trail.intensity_at(cell) for cell in board.cells()}
        facts = Facts(board, thief, belief(cop, step, thief), step, horizon - step, own)
        move = brain.pick_move(facts)
        row, col = board.delta_for(move)
        landing = (thief[0] + row, thief[1] + col)
        # The orchestrator filters illegality, so a brain never actually walks
        # into a wall. Mirroring that here keeps a scoring regression from
        # hiding behind an illegal escape.
        thief = landing if board.is_open(landing) else thief
        path.append(thief)
        trail.decay_all()
        trail.deposit(thief)
        if thief == cop:
            return DuelResult(step, True, tuple(path), "walked into the cop")

    return DuelResult(horizon, False, tuple(path), "survived")
