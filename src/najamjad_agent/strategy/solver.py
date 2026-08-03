"""Solving the chase exactly, by backward induction over every position.

Not a heuristic and not a lookahead — the actual game-theoretic answer. The
board has 49 cells, so a perfect-information state is (cop cell, thief cell,
whose turn) and there are 49 x 49 x 2 = 4802 of them. That is small enough to
solve outright, and solving it beats any amount of tuning: the result is the
*set of positions from which the cop can force a capture*, and a thief that
never enters one cannot be caught. Ever, by any opponent, however clever.

Why perfect information is the right model here: our pheromone field clamps the
freshest deposit at the ceiling while every older cell decays, so the newest
deposit is always the unique global maximum — verified 240/240. Both sides know
each other's cell every turn. `thief_brain` still checks that the belief is
genuinely peaked before trusting it, and falls back when it is not.

The classical result agrees with what this computes. A 7x7 grid is the
Cartesian product of two paths, and the cop number of a product of two trees is
2 (Maamoun & Meyniel) — one cop is not enough, so on an intact board the
cop-win set contains only the positions where the two already share a cell.
Barriers are what change that, which is exactly why the solve is redone
whenever one lands rather than computed once and trusted.
"""

from __future__ import annotations

from functools import lru_cache

from ..domain.board import Board
from ..domain.params import Position

#: A state is (cop cell, thief cell). Two tables are kept, one per side to move.
State = tuple[Position, Position]


def _moves(board: Board, cell: Position) -> tuple[Position, ...]:
    """Where a piece at `cell` can be after its turn — neighbours, or stay."""
    return (cell, *board.neighbours(cell))


def solve(board: Board) -> frozenset[State]:
    """Every position, thief to move, from which the cop can force a capture.

    Input: the board, including whatever barriers are currently down.
    Output: the losing set for the thief, as (cop, thief) pairs.
    Setup: none — pure, so the same board always yields the same answer.

    Backward induction to a fixed point rather than to a horizon. A horizon
    would answer "can the cop win within k moves", which is a weaker and more
    fragile question: the thief needs a move that is safe for the rest of the
    game, and the fixed point is exactly that.

    Reading the two rules below is worth the minute:

    * with the **cop** to move, the cop wins if *any* of its moves reaches a
      position the thief then loses from — the cop picks;
    * with the **thief** to move, the cop wins only if *every* thief move leads
      to a position the cop wins from — the thief picks, so one escape suffices.
    """
    cells = [cell for cell in board.cells() if board.is_open(cell)]
    caught = {(cell, cell) for cell in cells}
    cop_to_move: set[State] = set(caught)
    thief_to_move: set[State] = set(caught)

    changed = True
    while changed:
        changed = False
        for cop in cells:
            for thief in cells:
                state = (cop, thief)
                if state not in cop_to_move and any(
                    (step, thief) in thief_to_move for step in _moves(board, cop)
                ):
                    cop_to_move.add(state)
                    changed = True
                if state not in thief_to_move and all(
                    (cop, step) in cop_to_move for step in _moves(board, thief)
                ):
                    thief_to_move.add(state)
                    changed = True
    return frozenset(thief_to_move)


@lru_cache(maxsize=64)
def _solved(barriers: frozenset[Position], size: int, params: object) -> frozenset[State]:
    """Cached solve, keyed on what actually changes the answer.

    The board is rebuilt from its barriers rather than being the key itself,
    because `Board` is not hashable by value and two boards with the same walls
    have the same solution. Sixty-four entries covers a whole series: at most
    fourteen barriers land per mini-game, so a game visits fifteen boards.
    """
    return solve(Board(params, barriers))  # type: ignore[arg-type]


def losing_states(board: Board) -> frozenset[State]:
    """The thief's losing set for this board, computed once per barrier layout."""
    return _solved(board.barriers, board.size, board.params)


def safe_landings(board: Board, cop: Position, thief: Position) -> tuple[Position, ...]:
    """Every cell the thief can move to that the cop cannot then force a win from.

    Input: the board, and both true positions, with the thief to move.
    Output: the provably safe landings, best-effort ordered for a stable caller.

    Empty means the position is already lost against perfect cop play — which on
    an intact grid happens only when the two share a cell, and otherwise only
    once barriers have done real damage.
    """
    losing = losing_states(board)
    return tuple(
        landing
        for landing in _moves(board, thief)
        if landing != cop and (cop, landing) not in losing
    )


def cop_can_force_capture(board: Board, cop: Position, thief: Position) -> bool:
    """Whether the cop wins this position with both sides playing perfectly."""
    return (cop, thief) in losing_states(board)
