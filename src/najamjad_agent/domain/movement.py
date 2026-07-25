"""Move application, legality filtering, the Barrier Law, and physics policing.

Two responsibilities that must never be confused:

* **Our moves** go through `apply_move`/`legal_moves`, which make an illegal
  move *unrepresentable* — the strategy layer can only choose from the legal
  set, so a hallucinating LLM can never cost us a technical loss (book rule 25).
* **Their moves** go through `validate_opponent_step`. There is no referee, so
  each peer enforces physics on the other (book rules 13-14); a violation is
  returned as a reason string for the protocol layer to escalate.
"""

from dataclasses import dataclass

from ..constants import Move, Role
from .board import Board
from .params import Position


class IllegalMoveError(Exception):
    """Raised when a move or barrier placement breaks the agreed physics."""

    def __init__(self, reason: str, detail: str = "") -> None:
        """Store a machine-readable `reason` alongside the human message."""
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class BarrierPlacement:
    """Result of a lawful barrier placement, with its mandatory declaration."""

    board: Board
    cell: Position

    @property
    def declaration(self) -> dict:
        """Truthful public announcement of the exact cell (book rules 15-16)."""
        return {"barrier_placed": [self.cell[0], self.cell[1]]}


def _coerce_move(move: Move | str) -> Move:
    """Accept only the fixed move vocabulary; anything else is illegal input."""
    try:
        return Move(move)
    except ValueError as error:
        raise IllegalMoveError("unknown move", str(move)) from error


def apply_move(board: Board, position: Position, move: Move | str) -> Position:
    """Return the cell reached by `move`, or raise if the step is illegal."""
    chosen = _coerce_move(move)
    row_delta, col_delta = board.delta_for(chosen)
    target = (position[0] + row_delta, position[1] + col_delta)
    if not board.in_bounds(target):
        raise IllegalMoveError("off-board", f"{position} -> {target}")
    if board.is_blocked(target):
        raise IllegalMoveError("barrier", f"{target} is impassable")
    return target


def legal_moves(board: Board, position: Position, mobile_only: bool = False) -> tuple[Move, ...]:
    """Every move available from `position`; `mobile_only` drops STAY.

    An empty result under `mobile_only` is the immobilisation signal used by
    the capture rules (book rule 47) — STAY itself is never blocked.
    """
    available = []
    for move in Move:
        if mobile_only and move is Move.STAY:
            continue
        try:
            apply_move(board, position, move)
        except IllegalMoveError:
            continue
        available.append(move)
    return tuple(available)


def place_barrier(board: Board, role: Role, actor: Position, target: Position) -> BarrierPlacement:
    """Apply the Barrier Law: cop-only, within one orthogonal step, budgeted."""
    if role is not Role.COP:
        raise IllegalMoveError("cop only", "barriers are the cop's asymmetric power")
    if board.barrier_count >= board.params.max_barriers:
        raise IllegalMoveError("budget exhausted", f"quota {board.params.max_barriers} spent")
    if not board.in_bounds(target):
        raise IllegalMoveError("off-board", f"{target}")
    if board.is_blocked(target):
        raise IllegalMoveError("already blocked", f"{target}")
    if Board.manhattan(actor, target) > 1:
        raise IllegalMoveError("out of reach", f"{actor} -> {target} exceeds one orthogonal step")
    return BarrierPlacement(board.with_barrier(target), target)


def validate_opponent_step(board: Board, previous: Position, current: Position) -> str | None:
    """Police the opponent's declared step; return a reason string if invalid."""
    if not board.in_bounds(current):
        return "off-board"
    if board.is_blocked(current):
        return "barrier"
    row_delta = abs(current[0] - previous[0])
    col_delta = abs(current[1] - previous[1])
    if row_delta == 0 and col_delta == 0:
        return None
    if row_delta == 1 and col_delta == 1:
        return "diagonal"
    if row_delta + col_delta != 1:
        return "teleport"
    return None
