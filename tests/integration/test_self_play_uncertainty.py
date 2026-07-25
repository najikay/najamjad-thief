"""Self-play under *realistic* information — the condition the league plays in.

`test_self_play.py` gives both brains perfect knowledge of the opponent. That is
a useful upper bound but not the game: belief actually comes from a decaying
scent field and a hint that may be a lie, so it is always smeared across several
cells.

The distinction turned out to matter. With perfect information our cop captures
from every start; blur the belief by even one cell — far less uncertainty than a
real scent map — and the thief survives. Anyone reading only the perfect-info
numbers would badly overestimate the cop and underestimate the thief.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.fakes.orchestration import build_state
from tests.integration.test_self_play import Facts, GreedyCop, GreedyThief

SURVIVAL_STEPS = 35


def blurred_belief(board: Board, truth, spread: int) -> dict:
    """Uniform belief over cells within `spread` steps of the truth.

    A crude stand-in for a scent-derived posterior, and deliberately generous to
    the observer: a real scent map is noisier than this.
    """
    cells = [
        cell
        for cell in board.cells()
        if board.is_open(cell) and Board.manhattan(cell, truth) <= spread
    ]
    if not cells:
        return {truth: 1.0}
    return dict.fromkeys(cells, 1.0 / len(cells))


def play_blurred(cop_brain, thief_brain, spread: int, cop_start=(0, 0), thief_start=(3, 3)) -> str:
    """One mini-game where neither side sees the other exactly."""
    board: Board = build_state(Role.COP).board
    cop, thief, barriers_left = cop_start, thief_start, 14

    for _ in range(SURVIVAL_STEPS):
        thief_facts = Facts(board, thief, blurred_belief(board, cop, spread), role="thief")
        move = thief_brain.pick_move(thief_facts)
        row, col = board.delta_for(move)
        candidate = (thief[0] + row, thief[1] + col)
        thief = candidate if board.is_open(candidate) else thief
        if thief == cop:
            return "capture"

        cop_facts = Facts(
            board, cop, blurred_belief(board, thief, spread), barriers_left=barriers_left
        )
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


@pytest.mark.parametrize("spread", [1, 2, 3])
def test_our_thief_survives_our_own_cop_under_realistic_uncertainty(spread: int) -> None:
    """The finding worth recording: perfect info flatters the cop enormously."""
    assert play_blurred(CopBrain(), ThiefBrain(), spread) == "survival"


def test_perfect_information_is_an_unrealistic_upper_bound() -> None:
    """Same brains, same start — only the information changes the outcome."""
    assert play_blurred(CopBrain(), ThiefBrain(), spread=0) == "capture"
    assert play_blurred(CopBrain(), ThiefBrain(), spread=1) == "survival"


@pytest.mark.parametrize("spread", [1, 2])
def test_our_thief_still_beats_the_greedy_cop_under_uncertainty(spread: int) -> None:
    assert play_blurred(GreedyCop(), ThiefBrain(), spread) == "survival"


@pytest.mark.parametrize("spread", [1, 2])
def test_our_cop_is_never_worse_than_the_greedy_cop_under_uncertainty(spread: int) -> None:
    """Uncertainty must not turn our extra machinery into a liability."""
    ours = play_blurred(CopBrain(), GreedyThief(), spread)
    baseline = play_blurred(GreedyCop(), GreedyThief(), spread)
    outcomes = {"capture": 1, "survival": 0}
    assert outcomes[ours] >= outcomes[baseline]


def test_uncertainty_still_produces_deterministic_games() -> None:
    first = play_blurred(CopBrain(), ThiefBrain(), spread=2)
    assert play_blurred(CopBrain(), ThiefBrain(), spread=2) == first
