"""Capture rules and the thief's cryptographically-enforced truth duty.

Three ways a mini-game ends in capture (book Ch. 3, rules 46-47):
1. the cop enters the thief's cell **and declares a Capture Claim** — entering
   silently is not a capture;
2. the cop places a barrier on the cell the thief occupies;
3. the thief has no move that changes its cell (fully walled in).

`answer_capture_claim` is the only place a capture answer is produced, and it
reads the thief's true cell. A dishonest answer is therefore not expressible in
code — which matters because the answer is sealed into the commit and would be
exposed at audit (book rules 21-22).
"""

from dataclasses import dataclass

from ..constants import EndReason
from .board import Board
from .movement import legal_moves
from .params import Position


@dataclass(frozen=True)
class CaptureVerdict:
    """Outcome of evaluating the capture rules for one step."""

    captured: bool
    reason: str = ""

    @property
    def end_reason(self) -> EndReason | None:
        """The mini-game end reason, or None when play continues."""
        return EndReason.CAPTURE if self.captured else None


def evaluate_capture(
    board: Board,
    cop_cell: Position,
    thief_cell: Position,
    capture_claim: bool,
) -> CaptureVerdict:
    """Decide whether this step captured the thief."""
    if is_immobilised(board, thief_cell):
        return CaptureVerdict(True, "immobilised")
    if cop_cell == thief_cell:
        # Co-location alone is not enough: the cop must claim it out loud.
        return CaptureVerdict(True, "claim") if capture_claim else CaptureVerdict(False, "unclaimed")
    return CaptureVerdict(False)


def evaluate_barrier_capture(barrier_cell: Position, thief_cell: Position) -> CaptureVerdict:
    """A barrier dropped on the thief's own cell captures it (book rule 46)."""
    if barrier_cell == thief_cell:
        return CaptureVerdict(True, "barrier")
    return CaptureVerdict(False)


def is_immobilised(board: Board, thief_cell: Position) -> bool:
    """True when the thief cannot reach any neighbouring cell (book rule 47)."""
    return legal_moves(board, thief_cell, mobile_only=True) == ()


def answer_capture_claim(true_thief_cell: Position, claimed_cell: Position) -> bool:
    """Answer a Capture Claim truthfully from the thief's real position.

    Single source of truth for capture answers: no caller may substitute a
    different cell, so the sealed record can never contain a lie.
    """
    return tuple(true_thief_cell) == tuple(claimed_cell)


def resolve_survival(steps_taken: int, params_survival_threshold: int, max_moves: int) -> EndReason | None:
    """End the mini-game when the thief has outlasted the agreed step budget.

    The book leaves the step-cap outcome undefined while setting cap and
    survival threshold to the same value; per PRD A2 we treat reaching either
    as thief survival and document the interpretation (book Open-Q 5).
    """
    if steps_taken >= min(params_survival_threshold, max_moves):
        return EndReason.SURVIVAL
    return None
