"""Reacting cops for the thief bench, and the duel that runs them.

`duel.run_duel` replays a recorded cop line, and a recorded line cannot
answer the question counted #6 asked: ahk-yosi's cop was not following a
script, it was *reacting* — pursue on the shortest path, hold a zugzwang STAY
at distance two, spend one wall on a pinched thief's exit, take whatever
remains. Our thief, replayed against its recorded line, survives; against the
policy that produced the line it died three times, byte-identically.

`CornerHunter` is that policy, parameterised by its pursuit tie-break so it
is a family of twenty-four and not one solvable line. `duel_react` runs the
book order — thief moves first, then the cop moves or walls — with perfect
information on both sides, which overstates the cop and is therefore the safe
direction for a thief bench.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.domain.params import GameParams, Position
from najamjad_agent.strategy.territory import distances_from

UNREACHED = 10**6


class _ThiefFacts:
    def __init__(self, board: Board, position: Position, cop: Position,
                 step: int, left: int) -> None:
        self.board = board
        self.own_position = position
        self.belief = {cop: 1.0}
        self.scent: dict[Position, float] = {}
        self.own_scent: dict[Position, float] = {}
        self.legal = legal_moves(board, position)
        self.barriers_left = 0
        self.role = "thief"
        self.step = step
        self.steps_remaining = left
        self.sub_game = 1


def _apply(board: Board, cell: Position, move: Move) -> Position:
    row, col = board.delta_for(move)
    landing = (cell[0] + row, cell[1] + col)
    return landing if board.is_open(landing) else cell


class CornerHunter:
    """Pursue, hold the zugzwang, wall one exit of a pinched thief, take."""

    def __init__(self, tie: tuple[Move, ...] = (Move.EAST, Move.SOUTH,
                                                Move.NORTH, Move.WEST)) -> None:
        self.tie = {move: index for index, move in enumerate(tie)}

    def act(self, board: Board, cop: Position, thief: Position,
            walls_left: int) -> tuple[str, Position]:
        for move in legal_moves(board, cop):
            if _apply(board, cop, move) == thief:
                return ("move", thief)
        exits = [cell for cell in board.neighbours(thief) if cell != cop]
        gap = distances_from(board, cop).get(thief, UNREACHED)
        if walls_left and gap <= 2 and len(exits) <= 2:
            allowed = {cell for cell in (cop, *board.neighbours(cop))
                       if board.is_open(cell)}
            for cell in sorted(exits):
                if cell in allowed and cell != thief:
                    return ("wall", cell)
            if gap == 2:
                return ("move", cop)        # zugzwang: force the thief to move
        reach = distances_from(board, thief)
        best, key = cop, None
        for move in legal_moves(board, cop):
            landing = _apply(board, cop, move)
            score = (reach.get(landing, UNREACHED), self.tie.get(move, 9))
            if key is None or score < key:
                best, key = landing, score
        return ("move", best)


def duel_react(thief_brain: Any, cop_policy: Any,
               params: GameParams) -> tuple[int, bool, str]:
    """Book order per step: thief moves, then the cop moves or walls."""
    board = Board(params)
    thief, cop = params.thief_start, params.cop_start
    walls_left = params.max_barriers
    horizon = min(params.survival_threshold, params.max_moves)
    for step in range(1, horizon + 1):
        facts = _ThiefFacts(board, thief, cop, step, horizon - step)
        move = thief_brain.pick_move(facts)
        thief = _apply(board, thief, move if move in facts.legal else Move.STAY)
        if thief == cop:
            return step, True, "walked into the cop"
        kind, cell = cop_policy.act(board, cop, thief, walls_left)
        if kind == "wall" and walls_left and board.is_open(cell) and cell != thief:
            board = board.with_barrier(cell)
            walls_left -= 1
        else:
            cop = cell
        if cop == thief:
            return step, True, "stepped on"
        if not board.neighbours(thief):
            return step, True, "immobilised (rule 47)"
    return horizon, False, "survived"
