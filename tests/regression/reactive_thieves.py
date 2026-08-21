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


class Evader:
    """A thief that always steps to the legal cell furthest from the cop.

    The instrument that matters. A *recorded* thief line does not react: replay
    vibecode's real 35 cells against our cop and it captures at step 13, while
    the live series it came from stalled at distance 2 for 28 steps. The line is
    identical; the difference is entirely that the real thief was responding to
    where our cop actually went.

    So a scripted replay measures "can we follow a path" and cannot measure "can
    we close on something that runs". This is the greedy-evasion baseline for
    the second question, and it is deliberately simple — a thief this dumb still
    exposes the pursuit deadlock, which is the point.
    """

    def pick_move(self, facts: Any) -> Move:
        board, here = facts.board, facts.own_position
        cop = facts.cop_position
        best, best_score = Move.STAY, -1
        for move in sorted(facts.legal, key=lambda option: option.value):
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if not board.is_open(landing):
                continue
            score = Board.manhattan(landing, cop)
            if score > best_score:
                best, best_score = move, score
        return best


class GapDancer:
    """Anti-seal specialist: hold the furthest gap of the fence, else keep room."""

    def pick_move(self, facts: Any) -> Move:
        from najamjad_agent.strategy.territory import distances_from, fence_gaps

        board, here, cop = facts.board, facts.own_position, facts.cop_position
        gaps = fence_gaps(board, cop)
        reach_cop = distances_from(board, cop)
        best, key = Move.STAY, None
        for move in sorted(facts.legal, key=lambda option: option.value):
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if not board.is_open(landing):
                continue
            safe = reach_cop.get(landing, 10**6)
            if safe < 2:
                continue
            goal = -distances_from(board, landing).get(gaps[0], 10**6) if gaps else 0
            candidate = (min(safe, 3), goal, component_size(board, landing))
            if key is None or candidate > key:
                best, key = move, candidate
        return best


class SideKeeper:
    """Keeps distance and the room left after the cop's best single wall."""

    def pick_move(self, facts: Any) -> Move:
        from najamjad_agent.strategy.territory import distances_from

        board, here, cop = facts.board, facts.own_position, facts.cop_position
        reach_cop = distances_from(board, cop)
        best, key = Move.STAY, None
        for move in sorted(facts.legal, key=lambda option: option.value):
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if not board.is_open(landing):
                continue
            safe = reach_cop.get(landing, 10**6)
            if safe < 2:
                continue
            worst = component_size(board, landing)
            for cell in (cop, *board.neighbours(cop)):
                if board.is_open(cell) and cell != landing:
                    worst = min(worst, component_size(board.with_barrier(cell), landing))
            candidate = (min(safe, 3), worst, component_size(board, landing))
            if key is None or candidate > key:
                best, key = move, candidate
        return best


class ColumnSquatter:
    """Squats the open column-3 cell furthest from the cop, dodging eviction.

    The script-aware adversary: it camps the cells the halving plan wants to
    wall, which the Barrier Law protects while occupied. A seal that cannot
    survive its own line being squatted is a seal an informed opponent solves.
    """

    def pick_move(self, facts: Any) -> Move:
        from najamjad_agent.strategy.territory import distances_from

        board, here, cop = facts.board, facts.own_position, facts.cop_position
        reach_cop = distances_from(board, cop)
        targets = [(row, 3) for row in range(board.size) if board.is_open((row, 3))]
        best, key = Move.STAY, None
        for move in sorted(facts.legal, key=lambda option: option.value):
            row, col = board.delta_for(move)
            landing = (here[0] + row, here[1] + col)
            if not board.is_open(landing):
                continue
            safe = reach_cop.get(landing, 10**6)
            if safe < 2:
                continue
            mine = distances_from(board, landing)
            near = min((mine.get(target, 10**6) for target in targets), default=0)
            candidate = (min(safe, 2), -near, landing[1])
            if key is None or candidate > key:
                best, key = move, candidate
        return best
