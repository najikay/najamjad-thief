"""Thieves that see the live board, for questions a replayed line cannot answer.

`scripted_opponents.py` holds real lines, and they are the better evidence for
anything about pursuit. They cannot decide anything about **barriers**: a
replayed line is a list of cells the thief is teleported through, so it walks
through the walls we place while they still block us — 36 of the 56 archived
lines put the thief on a cell we had walled. Measured on that instrument, every
barrier is pure cost, which is how `barrier_threshold` came to be tuned to a
value that declined eleven walls of fourteen in a counted series we lost.

These two react. `RandomThief` is the faithful model of this league — moaamoha's
own sealed records carry `"random_move": true` on the steps we captured them —
and `RoomEvader` is the adversary a wall policy actually has to beat: it keeps
its distance *and* the room it keeps, which is what enclosure takes away.
"""

from __future__ import annotations

import random
from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.territory import component_size


class RandomThief:
    """Picks a legal move at random, optionally fleeing some of the time."""

    def __init__(self, seed: int, flee: float = 0.0) -> None:
        self.rng = random.Random(seed)
        self.flee = flee

    def pick_move(self, facts: Any) -> Move:
        board, here, cop = facts.board, facts.own_position, facts.cop_position
        options = []
        for move in facts.legal:
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if board.is_open(landing):
                options.append((move, Board.manhattan(landing, cop)))
        if not options:
            return Move.STAY
        if self.flee and self.rng.random() < self.flee:
            furthest = max(distance for _move, distance in options)
            options = [(move, d) for move, d in options if d == furthest]
        return self.rng.choice(options)[0]


class RoomEvader:
    """Keeps its distance, and breaks ties by the room it keeps.

    Distance is capped at three because beyond that the cop cannot reach us next
    turn however far we run, so the rest of the choice is about not being sealed
    in. Deliberately not our own thief: a wall policy measured only against the
    brain it was tuned beside has been measured against itself.
    """

    def pick_move(self, facts: Any) -> Move:
        board, here, cop = facts.board, facts.own_position, facts.cop_position
        best, best_key = Move.STAY, (-1, -1)
        for move in sorted(facts.legal, key=lambda option: option.value):
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if not board.is_open(landing):
                continue
            key = (min(Board.manhattan(landing, cop), 3), component_size(board, landing))
            if key > best_key:
                best, best_key = move, key
        return best
