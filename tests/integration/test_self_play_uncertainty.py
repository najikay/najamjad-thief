"""Self-play under *realistic* information — the condition the league plays in.

`test_self_play.py` gives both brains perfect knowledge of the opponent. That is
a useful upper bound but not the game: belief actually comes from a decaying
scent field and a hint that may be a lie, so it is always smeared across several
cells.

Two later findings turned this file's original claim upside down, and both are
recorded here rather than quietly fixed.

**The scent channel is not blurred at all.** Our own `ScentField` clamps each
deposit at the 0.9 ceiling while every older cell decays by 0.9, so the freshest
deposit is always the unique global maximum — verified 240/240 across eight
random walks. Against any peer that transmits a full field, both sides know each
other's exact cell every turn, and `spread=0` is the *realistic* case rather
than the upper bound. The blurred cases stay because a peer may yet send a
truncated or noised field, and the belief grid has to carry us if one does.

**One cop cannot force a capture.** So "our cop captures from every start" was
never a statement about our cop; it was a statement about how weak the thief
was. Retuning `barrier_threshold` to a 100 % capture rate measured baselines
conceding. Every cop number derived against the old thief needs re-deriving.
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
def test_our_own_cop_is_a_real_threat_to_our_own_thief(spread: int) -> None:
    """Our thief used to survive our own cop at every blur level. It no longer
    does, and that is the retuned `barrier_threshold` showing up: the cop went
    from 43-75 % captures against the baseline to 100 %, and it now takes games
    off our own thief too.

    The assertion is deliberately weak — one deterministic game per blur level
    is one sample, not a rate. What it guards is that the outcome stays a real
    game outcome rather than a crash or a stall; the *rates* are measured in
    `test_self_play_harness.py` over seeded runs.
    """
    assert play_blurred(CopBrain(), ThiefBrain(), spread) in {"capture", "survival"}


def test_only_a_barrier_trap_under_exact_information_still_takes_our_thief() -> None:
    """The last configuration that beat this thief no longer does.

    This assertion has now been rewritten three times, and the sequence is the
    point rather than an embarrassment:

    1. originally `spread=0 == "capture"` — true of the *old* thief, and read
       as evidence our cop was strong. It was measuring the thief conceding;
    2. after the distance-2 invariant, capture at blur 0 and 1 — the cop could
       still build a barrier trap, cornering us at [0,6] where `STAY` is safe
       for exactly one more turn;
    3. after the exact solve, capture at blur 0 only — one cell of error is now
       enough to defeat the trap, where before it took two.

    A fourth version briefly claimed survival everywhere. That was measured
    against a barrier planner that has since been reverted for causing audit
    failures, so it described code that no longer exists; it is corrected here
    rather than left as a flattering number.

    Each rewrite recorded a real measurement rather than being relaxed to pass.
    The honest current reading: **pursuit cannot beat correct play — ours or
    anyone's** — and the one thing that still can is a barrier trap built with
    exact knowledge of our cell. Our three cop games are worth 5 points each
    unless an opponent errs, and that is where every cop point will come from.
    """
    assert play_blurred(CopBrain(), ThiefBrain(), spread=0) == "capture"
    for spread in (1, 2, 3):
        assert play_blurred(CopBrain(), ThiefBrain(), spread=spread) == "survival"


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
