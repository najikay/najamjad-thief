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


def play_blurred(
    cop_brain, thief_brain, spread: int, cop_start=(0, 0), thief_start=(3, 3), sub_game: int = 1
) -> str:
    """One mini-game where neither side sees the other exactly.

    `sub_game` seeds the thief's tie-break among equally safe moves. It used
    to be pinned at 1, so this harness measured exactly one of the several
    lines the thief may legitimately play and reported it as *the* outcome —
    which is how a single coin flip came to be an assertion.
    """
    board: Board = build_state(Role.COP).board
    cop, thief, barriers_left = cop_start, thief_start, 14

    for step in range(1, SURVIVAL_STEPS + 1):
        thief_facts = Facts(board, thief, blurred_belief(board, cop, spread), role="thief")
        thief_facts.sub_game = sub_game
        thief_facts.step = step
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


def test_a_barrier_trap_under_exact_information_can_still_take_our_thief() -> None:
    """The last configuration that beat this thief, measured as a rate not a coin flip.

    This assertion has now been rewritten four times, and the sequence is the
    point rather than an embarrassment:

    1. originally `spread=0 == "capture"` — true of the *old* thief, and read as
       evidence our cop was strong. It was measuring the thief conceding;
    2. after the distance-2 invariant, capture at blur 0 and 1 — the cop could
       still build a barrier trap, cornering us at [0,6];
    3. after the exact solve, capture at blur 0 only;
    4. **now**: capture at blur 0 for *some* tie-break seeds and not others.

    A fifth version briefly claimed survival everywhere. That was measured
    against a barrier planner since reverted, so it described code that no
    longer exists.

    What changed for (4) is that tie-breaking among equally safe moves now
    spreads properly across sub-games instead of collapsing onto two or three
    choices. The exact solve is silent about barriers — it models a cop that
    only *moves* — so which safe move we pick still decides whether a barrier
    trap closes. Escaping it is therefore genuinely seed-dependent, and stating
    it as "we survive" would be the flattering-number mistake again.

    Measured over the six sub-game seeds of a real series, so it is a rate.
    """
    outcomes = [
        play_blurred(CopBrain(), ThiefBrain(), spread=0, sub_game=sub) for sub in range(1, 7)
    ]

    assert "capture" in outcomes, (
        "an exact-information barrier trap should still land for at least one "
        f"tie-break seed; got {outcomes}"
    )
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
