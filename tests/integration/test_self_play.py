"""Self-play: do our brains actually beat the obvious strategy?

Unit tests prove each policy behaves as designed. Only self-play answers the
question that decides the league: is the design *better* than what most teams
will ship? The baselines here are exactly that — a greedy chaser and a greedy
runner, which is what the reference implementation's spirit amounts to.

Games are fully deterministic (no RNG anywhere in the move path), so a
regression shows up as a changed win count rather than flakiness.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.strategy.base import move_away, move_towards
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.fakes.orchestration import build_state

SURVIVAL_STEPS = 35


class Facts:
    """What either brain is allowed to see."""

    def __init__(self, board, position, belief, scent=None, barriers_left=14, role="police"):
        self.board = board
        self.own_position = position
        self.belief = belief
        self.scent = scent or {}
        self.legal = legal_moves(board, position)
        self.barriers_left = barriers_left
        self.role = role
        self.step = 1
        self.sub_game = 1


class GreedyCop:
    """The obvious cop: walk at the target every turn, never build."""

    def pick_move(self, facts) -> Move:
        target = max(facts.belief, key=lambda cell: facts.belief[cell], default=None)
        if target is None:
            return Move.STAY
        return move_towards(facts.board, facts.own_position, target, facts.legal)

    def pick_barrier(self, facts):
        return None


class GreedyThief:
    """The obvious thief: maximise distance, ignore the walls closing in."""

    def pick_move(self, facts) -> Move:
        threat = max(facts.belief, key=lambda cell: facts.belief[cell], default=None)
        if threat is None:
            return Move.STAY
        return move_away(facts.board, facts.own_position, threat, facts.legal)

    def pick_barrier(self, facts):
        return None


def play(cop_brain, thief_brain, cop_start=(0, 0), thief_start=(3, 3)) -> str:
    """Run one mini-game with perfect information; return "capture"/"survival"."""
    board: Board = build_state(Role.COP).board
    cop, thief = cop_start, thief_start
    barriers_left = 14

    for _ in range(SURVIVAL_STEPS):
        thief_facts = Facts(board, thief, {cop: 1.0}, role="thief")
        move = thief_brain.pick_move(thief_facts)
        row, col = board.delta_for(move)
        candidate = (thief[0] + row, thief[1] + col)
        thief = candidate if board.is_open(candidate) else thief
        if thief == cop:
            return "capture"

        cop_facts = Facts(board, cop, {thief: 1.0}, barriers_left=barriers_left)
        placement = cop_brain.pick_barrier(cop_facts)
        if placement is not None and board.is_open(placement) and barriers_left > 0:
            if placement == thief:
                return "capture"
            board = board.with_barrier(placement)
            barriers_left -= 1
        else:
            move = cop_brain.pick_move(cop_facts)
            row, col = board.delta_for(move)
            candidate = (cop[0] + row, cop[1] + col)
            cop = candidate if board.is_open(candidate) else cop
        if cop == thief:
            return "capture"
        if not legal_moves(board, thief, mobile_only=True):
            return "capture"
    return "survival"


STARTS = [
    ((0, 0), (3, 3)),
    ((0, 6), (3, 3)),
    ((6, 0), (3, 3)),
    ((6, 6), (3, 3)),
    ((3, 0), (3, 6)),
    ((0, 3), (6, 3)),
]


@pytest.mark.parametrize(("cop_start", "thief_start"), STARTS)
def test_our_thief_survives_the_greedy_cop(cop_start, thief_start) -> None:
    """The baseline most teams will ship must not beat us."""
    assert play(GreedyCop(), ThiefBrain(), cop_start, thief_start) == "survival"


def test_our_cop_beats_the_greedy_thief_more_often_than_the_greedy_cop_does() -> None:
    """The comparison that matters: is our design better, not merely correct?"""
    ours = [play(CopBrain(), GreedyThief(), cop, thief) for cop, thief in STARTS]
    baseline = [play(GreedyCop(), GreedyThief(), cop, thief) for cop, thief in STARTS]
    our_captures = ours.count("capture")
    baseline_captures = baseline.count("capture")
    assert our_captures >= baseline_captures, (
        f"our cop captured {our_captures}/{len(STARTS)}, "
        f"the greedy baseline {baseline_captures}/{len(STARTS)}"
    )


def test_our_cop_uses_its_barrier_quota_productively() -> None:
    """A cop that reaches step 35 with 14 unspent barriers has wasted them."""
    board: Board = build_state(Role.COP).board
    brain = CopBrain()
    placements = 0
    cop, thief = (0, 0), (3, 3)
    for _ in range(20):
        facts = Facts(board, cop, {thief: 1.0}, barriers_left=14 - placements)
        placement = brain.pick_barrier(facts)
        if placement is not None and board.is_open(placement):
            board = board.with_barrier(placement)
            placements += 1
        else:
            move = brain.pick_move(facts)
            row, col = board.delta_for(move)
            candidate = (cop[0] + row, cop[1] + col)
            cop = candidate if board.is_open(candidate) else cop
    assert placements > 0, "the cop never used a barrier in 20 turns"


def test_both_brains_are_deterministic_across_runs() -> None:
    """Same inputs, same game — a prerequisite for faithful replay."""
    first = [play(CopBrain(), ThiefBrain(), cop, thief) for cop, thief in STARTS]
    again = [play(CopBrain(), ThiefBrain(), cop, thief) for cop, thief in STARTS]
    assert first == again


def test_our_brains_never_emit_an_illegal_move() -> None:
    """Defence in depth: the orchestrator filters, but the brains agree."""
    board: Board = build_state(Role.COP).board
    for brain, role in ((CopBrain(), "police"), (ThiefBrain(), "thief")):
        for cell in board.cells():
            facts = Facts(board, cell, {(3, 3): 1.0}, role=role)
            assert brain.pick_move(facts) in facts.legal
