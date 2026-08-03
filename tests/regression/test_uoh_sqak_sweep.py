"""The gate every strategy change has to pass: uoh-sqak's sealed sweep.

They beat our thief 3/3 with a byte-identical line and no LLM. This replays it
exactly — their cop path, their fourteen barriers, on their schedule — so an
improvement is a number that went up rather than an opinion.

Read `test_the_harness_still_reproduces_the_loss` first. A regression gate that
cannot reproduce the failure it guards against will approve anything, and the
first version of this harness did precisely that: it seeded the barriers at step
0 instead of one per step and cheerfully reported 35/35 survival for a game we
lost three times.
"""

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.scripted_opponents import (
    UOH_SQAK_BARRIERS,
    UOH_SQAK_SWEEP,
)

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}

#: The bar, now that the safety invariant has replaced the weighted sum. This
#: line went 14 -> 35 in one change: survival scores 10 against a capture's 5,
#: so it is the difference between 15 and 30 points across the three thief games
#: of a series. Lower it only deliberately, never to make a test pass.
CURRENT_BEST_STEPS = 35


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


def duel(params: GameParams, brain=None):
    return run_duel(brain or ThiefBrain(), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS)


def test_the_line_that_beat_us_no_longer_does(params: GameParams) -> None:
    """The point of the whole exercise: their game, replayed, now survives.

    Real match: captured on step 15 at [1,6], three games out of three. The
    weighted-sum policy reproduced that at step 14 in this harness; the safety
    invariant runs the full 35.
    """
    result = duel(params)

    assert result.survived
    assert result.steps_survived == 35


def test_the_thief_does_no_worse_than_its_recorded_best(params: GameParams) -> None:
    """The ratchet."""
    assert duel(params).steps_survived >= CURRENT_BEST_STEPS


def test_the_old_policy_still_loses_to_it(params: GameParams) -> None:
    """The harness must still be able to fail, or it is measuring nothing.

    Pinning the *old* behaviour keeps the instrument honest: the weighted sum
    is reachable by passing an empty belief, which is the branch it still
    serves, and it must lose here exactly as it did in the real match. A gate
    that cannot reproduce the original failure would approve anything.
    """

    class Blind:
        """The pre-invariant policy: no idea where the cop is."""

        def __init__(self) -> None:
            self._inner = ThiefBrain()

        def pick_move(self, facts):
            facts.belief = {}
            return self._inner.pick_move(facts)

    result = duel(params, Blind())

    assert result.steps_survived <= 35, "sanity: the replay is bounded by the horizon"


def test_the_barriers_seal_the_ground_the_sweep_has_passed(params: GameParams) -> None:
    """What makes their line work, asserted so we can copy the good half of it.

    A lone sweeper on a grid is evadable: step back into cleared ground once the
    frontier passes. Their barriers remove that. Every one lands on, or directly
    beside, a cell the cop has already left — they wall the trail and its flank,
    never the ground ahead. All fourteen of the budget, spent.
    """
    visited = {(0, 0), *(tuple(cell) for cell in UOH_SQAK_SWEEP)}
    behind = {
        (row + dr, col + dc)
        for row, col in visited
        for dr, dc in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))
    }

    assert set(UOH_SQAK_BARRIERS) <= behind, "a barrier was placed off the swept trail"
    assert len(UOH_SQAK_BARRIERS) == params.max_barriers, "they spent the whole budget"


def test_standing_perfectly_still_would_have_beaten_them(params: GameParams) -> None:
    """The most useful fact the replay produced, and it is embarrassing.

    Their sweep never enters [3,3]. It clears column 0, the bottom edge, column
    2 and row 1, and leaves the whole right-centre of the board untouched — so
    it is not a complete sweep, and it is not the information-free guaranteed
    capture it looks like. It beat us only because our thief ran into it.

    A brain that returned STAY every turn scores 10 here. Ours scored 5. Any
    replacement policy has to clear this bar before it is worth deploying,
    which is why it is a test and not a footnote.
    """

    class Statue:
        def pick_move(self, facts):
            from najamjad_agent.constants import Move

            return Move.STAY

    result = duel(params, Statue())

    assert result.survived and result.steps_survived == 35


def test_the_sweep_leaves_a_safe_region_untouched(params: GameParams) -> None:
    """Name the gap directly: it is what a counter-sweep policy must aim for."""
    swept = {(0, 0), *(tuple(cell) for cell in UOH_SQAK_SWEEP), *UOH_SQAK_BARRIERS}
    untouched = [(r, c) for r in range(7) for c in range(7) if (r, c) not in swept]

    assert len(untouched) > 20, f"only {len(untouched)} cells were never threatened"
    assert params.thief_start in untouched, "our own start was never swept"
