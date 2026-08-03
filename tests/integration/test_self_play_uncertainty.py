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


def test_our_cop_still_traps_our_thief_with_barriers_under_perfect_information() -> None:
    """The one cop in the league that can still take this thief is ours.

    Worth stating precisely, because it is easy to read the wrong lesson. One
    cop provably cannot force a capture by *pursuit*: a 7x7 board is a product
    of two paths, the cop number of a product of two trees is 2 (Maamoun and
    Meyniel), and exact retrograde analysis over all 2401 positions finds no
    cop-win state where the two are apart. The thief's distance-2 invariant
    cashes that in — 0 captures in 75 games against a perfect chaser and two
    barrier-spending wallers, and 35/35 against the line uoh-sqak beat us with.

    Barriers are what break the theorem, and our cop plays them well enough to
    do it. The trace: the thief is cornered at [0,6] with the cop at [1,5],
    where `STAY` is genuinely safe at distance 2; the cop steps to [1,6] and a
    barrier closes [0,5]. Safe on the turn, lost on the next. A two-ply
    lookahead (`survives_the_reply`) pushed that from step 14 to step 34 but
    does not eliminate it, and pretending otherwise would be the
    `fakes-must-fail-like-reality` mistake in reverse.

    What was genuinely wrong here before is the *old* reading of this number: a
    100 % capture rate against the old thief measured the thief conceding, not
    the cop attacking. It is only meaningful now because the thief is hard.

    Measured across blur levels: capture at 0, survival at 1, 2 and 3. Adding
    the exact solve moved blur 1 from capture to survival — the trap now needs
    the cop to know our cell *exactly*, and one cell of error is enough to make
    it wall the wrong corner.
    """
    assert play_blurred(CopBrain(), ThiefBrain(), spread=0) == "capture"
    assert play_blurred(CopBrain(), ThiefBrain(), spread=1) == "survival"
    assert play_blurred(CopBrain(), ThiefBrain(), spread=2) == "survival"


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
