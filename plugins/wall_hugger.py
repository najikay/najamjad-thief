"""A worked example of a brain plugin (`docs/EXTENDING.md` §1).

Deliberately a *bad* strategy: it hugs walls, which is close to the worst thing
an evader can do. The point of the example is the wiring, and a plugin that also
happened to be a good idea would blur the two.

Enable it with:

    [strategy]
    thief_brain = "plugins.wall_hugger:WallHugger"
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.domain.movement import apply_move, legal_moves


class WallHugger:
    """Moves to whichever reachable cell has the fewest exits."""

    def __init__(self, board_supplier: Any = None, **_ignored: Any) -> None:
        """Accept and ignore any tuning the orchestrator passes.

        `**_ignored` matters: the wiring may hand a brain keyword arguments a
        plugin does not know about, and a plugin that raises on an unexpected
        keyword breaks whenever the shipped brains gain a field.
        """
        self._board = board_supplier

    def pick_move(self, facts: Any) -> Move:
        """Prefer the tightest corner in reach."""
        board = self._board() if self._board else facts.board
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        here = getattr(facts, "own_position", (0, 0))

        def exits(move: Move) -> int:
            """How open the cell this move lands on is."""
            return len(legal_moves(board, apply_move(board, here, move)))

        # `move.value` breaks ties so the choice is deterministic — replay is a
        # graded deliverable, and a brain that picks arbitrarily breaks it.
        return min(legal, key=lambda move: (exits(move), move.value))

    def pick_barrier(self, facts: Any) -> None:
        """Never place one; a thief has no barriers to spend."""
        return None
