"""The cop-side ratchet, and the reason a barrier can never take the thief.

A counted series was lost **as cop** on 2026-08-14 and there was no cop-side
harness to reproduce it with. `duel.py` runs our thief against a scripted cop;
this runs our cop against a thief, with the belief the real ingress path builds
from the thief's scent.

The numbers here are a floor, not a target. They exist so a strategy change has
to prove itself against something rather than against an argument — every
candidate tried on 2026-08-15 was measured against exactly these cases, and
three of four were adopted-then-reverted on the evidence.

**What the benchmark is not.** A recorded thief line does not react. Replaying
vibecode's real 35 cells, our cop captures at step 13; the live series those
cells came from stalled at distance 2 for 28 steps. The adaptive cases are the
ones that mean anything, and even they are weaker than a best-responding evader.
"""

from __future__ import annotations

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.shared.strength import SANDBAGGED
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import Evader, run_cop_duel

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
    },
}

#: Step by which our cop closes on our own thief. The one adaptive opponent the
#: shipped policy beats, and the number a change must not lose.
CATCHES_OUR_THIEF_BY = 22


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


def test_the_cop_still_catches_our_own_thief(params: GameParams) -> None:
    """The ratchet. Adaptive, and the only adaptive case the cop currently wins."""
    result = run_cop_duel(CopBrain(), [], params, thief_brain=ThiefBrain())

    assert result.captured, "the cop stopped catching our own thief"
    assert result.step <= CATCHES_OUR_THIEF_BY


def test_the_cop_tracks_even_when_it_cannot_close(params: GameParams) -> None:
    """Sensing and closing are different failures and must stay distinguishable.

    Against a greedy evader the cop does *not* capture — and that is a theorem
    rather than a defect. A 7x7 grid is the product of two paths, so its cop
    number is 2 (Maamoun and Meyniel), and an exhaustive fixed-point over all
    49x49 states finds no state from which a movement-only cop can force a
    capture. What the cop must still do is know where the thief is, because a
    strategy that fixes closing will be built on that belief.
    """
    result = run_cop_duel(CopBrain(), [], params, thief_brain=Evader())

    assert result.tracking >= 0.9, f"belief named the true cell only {result.tracking:.0%} of turns"


def test_a_sandbagged_cop_lays_no_barriers_and_does_not_close(params: GameParams) -> None:
    """Warm-ups must not leak the real policy — barriers are the real policy."""
    result = run_cop_duel(CopBrain(strength=SANDBAGGED), [], params, thief_brain=Evader())

    assert result.barriers_used == 0
    assert not result.captured


def test_the_harness_scores_only_captures_an_opponent_would_honour(params: GameParams) -> None:
    """The instrument must not credit a win no opponent concedes.

    The first version of this harness ended the game when a barrier landed on
    the thief's cell, and reported a cop that captured every opponent by step
    13. All of it was fiction. The course reference implements **no** barrier
    capture and **no** immobilisation check — `rules.py` has only `thief_result`
    and `is_captured`, which compares a claim against its own sealed position —
    and `domain/endings.own_barrier_capture` already refuses to end a game that
    way, having learned it against the reference: it kept playing while we
    closed the game, filed the capture, and read its silence at audit as
    tampering.

    So a barrier can shrink the board and never take the thief. Every opponent
    we have met is reference-derived, which makes this a property of the league
    rather than of one peer.
    """
    result = run_cop_duel(CopBrain(), [(3, 3)] * 35, params)

    assert result.reason in {"captured", "thief survived"}, (
        f"a capture the opponent would dispute was scored as a win: {result.reason}"
    )
