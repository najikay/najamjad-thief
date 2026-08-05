"""Alternating with the peer until someone's move ends the mini-game.

Separate from `MatchRunner` because it is the one piece of that class with no
dependency on the runner at all: given a conductor and a move budget, it is a
pure loop, and it is the piece most worth being able to read in isolation when
a game ends on the wrong step.
"""

from __future__ import annotations

from typing import Any

from ..constants import EndReason


def run_turn_loop(
    orchestrator: Any, max_moves: int, beat: Any = None
) -> EndReason | None:
    """Alternate turns until one ends the game; None means the budget ran out.

    Input: the mini-game's conductor, and the agreed `max_moves`.
    Output: the `EndReason` that ended it, or None for survival.
    Setup: none.

    The bound is `max_moves` full turns, not a `while True`: a peer that answers
    forever must not be able to keep us in a game the rules say has already been
    decided on survival.
    """
    for _ in range(max_moves + 1):
        first, second = (
            (orchestrator.take_turn, orchestrator.receive_turn)
            if orchestrator.moves_first
            else (orchestrator.receive_turn, orchestrator.take_turn)
        )
        for act in (first, second):
            if beat is not None:
                # Proof of life, per half-turn rather than per full turn: a
                # freeze that takes us out between our move and theirs is the
                # same freeze, and a watchdog that only heard from us every
                # other half would need twice the threshold to be sure.
                beat()
            ended = act()
            if ended is not None:
                return ended
    return None
