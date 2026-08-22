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
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel
from tests.regression.reactive_thieves import Evader, RandomThief, RoomEvader

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
    },
}

#: Steps our own thief survives against our own cop. It used to be caught at 22;
#: `thief_safety.LOCAL_ROOM_RADIUS` stopped the tie-breaker walking it into a
#: corner and it now runs the full horizon. The ratchet therefore moved to the
#: thief's side of the matchup — the honest place for it, since the two brains
#: are measured against each other and only one of them improved.
OUR_THIEF_SURVIVES_OUR_COP = 35


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


def test_our_thief_outlasts_our_cop(params: GameParams) -> None:
    """The ratchet, and both sides of it have moved since it was written.

    Our cop caught our thief at step 22 until 2026-08-15, stopped when the
    thief's tie-breaker stopped walking it into corners, and caught it again at
    step 27 on 2026-08-16 the moment `barrier_threshold` dropped to 0.22 and the
    barriers started being spent. It no longer does, because the thief now
    measures the room left after **two** cuts rather than one — a wall built
    over several turns is not a single barrier (`PRD_strategy_thief.md`).

    That is the intended end state: a lone pursuer provably cannot close on a
    thief that defends its room (ADR-021). The barrier assertion is what keeps
    this honest — without it the test would pass just as well if the cop quietly
    stopped walling, which is the state it was in when the thief's vulnerability
    went unnoticed for a week.
    """
    result = run_cop_duel(CopBrain(), [], params, thief_brain=ThiefBrain())

    # No assertion on barriers spent, and the reason is the point. It used to
    # demand at least one, so that this could not pass by the cop quietly
    # giving up on walls. Since the thief started keeping a 4x4 in reach before
    # the cop can cut it off, our cop spends **none** here — not because it
    # stopped trying but because it is never offered ground worth a wall. Same
    # symptom, opposite cause. The wall-spending guarantee moved to
    # `test_the_stalled_chase_starts_walling_and_the_young_one_does_not`, which
    # measures it against a thief that does give it the chance.
    assert not result.captured, f"our thief was caught at step {result.step}"
    assert result.step == OUR_THIEF_SURVIVES_OUR_COP


def test_the_cop_tracks_even_when_it_cannot_close(params: GameParams) -> None:
    """Sensing and closing are different failures and must stay distinguishable.

    The cop cannot *force* a capture against a thief that keeps its distance —
    that is a theorem rather than a defect. A 7x7 grid is the product of two
    paths, so its cop number is 2 (Maamoun and Meyniel), and an exhaustive
    fixed-point over all 49x49 states finds no state from which a movement-only
    cop can force one. What it must still do is know where the thief is, because
    everything that fixes closing is built on that belief — and our own thief,
    which does keep its distance, is the case that shows the difference
    (`test_our_thief_outlasts_our_cop`).
    """
    result = run_cop_duel(CopBrain(), [], params, thief_brain=Evader())

    assert result.tracking >= 0.9, f"belief named the true cell only {result.tracking:.0%} of turns"


def test_the_cop_takes_a_thief_that_lets_it_reach_striking_range(params: GameParams) -> None:
    """Closing is a separate ratchet from tracking, and it used to read zero.

    "One cop cannot force a capture" is true of a thief that never lets the
    distance fall to one. It was being reported about *every* thief, because
    this harness only ended a game when the thief walked into a stationary cop —
    the reverse of the move that decides real ones. Under the rule five real
    captures in the moaamoha series of 2026-08-15 were actually settled by (the
    thief moves, the cop steps onto the cell it moved to, and claims it), the
    same pursuit ends at step 13 rather than running to 35 at distance 1 for its
    last 23 steps.

    The greedy evader is a weak thief on purpose: it maximises distance from
    where the cop *is*, which walks it into a corner. A cop that cannot punish
    that has stopped pursuing, and no amount of tracking makes up for it.
    """
    result = run_cop_duel(CopBrain(), [], params, thief_brain=Evader())

    assert result.captured, f"the pursuit never finished: {result.reason} at {result.step}"
    assert result.step <= 13, f"closed at {result.step}, slower than the measured 13"


def test_the_cop_carries_no_strength_dial(params: GameParams) -> None:
    """The levels are gone (2026-08-22), not merely equal.

    This test's previous life asserted a sandbagged cop played the full
    policy; before that, the opposite. The dial's whole history was one of
    doing something other than what the operator believed, so its absence is
    now the assertion - a `strength` argument must fail loudly rather than
    be silently accepted and ignored.
    """
    import pytest

    with pytest.raises(TypeError):
        CopBrain(strength="sandbagged")


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


#: Starting positions for the barrier questions. The agreed terms fix cop [0,0]
#: and thief [3,3]; the rest are hypotheticals, used only to check that a dial's
#: advantage survives being moved off the one position it was found at.
BARRIER_STARTS = [((0, 0), (3, 3)), ((3, 3), (6, 6)), ((6, 6), (0, 0)), ((1, 1), (4, 4)),
                  ((0, 6), (6, 0)), ((2, 3), (4, 1)), ((5, 5), (1, 2)), ((4, 2), (1, 5))]


def _params(cop: tuple[int, int], thief: tuple[int, int]) -> GameParams:
    return GameParams.from_config({
        "board_and_agents": {"grid_size": 7, "thief_start": list(thief), "cop_start": list(cop)},
        "movement_and_barriers": CONFIG["movement_and_barriers"],
    })


def _captures(brain, build_thief, seeds=(0,)) -> int:
    return sum(
        run_cop_duel(brain(), [], _params(cop, thief), thief_brain=build_thief(seed)).captured
        for seed in seeds
        for cop, thief in BARRIER_STARTS
    )


def test_the_stalled_chase_starts_walling_and_the_young_one_does_not() -> None:
    """Both halves of the phase, against the two thieves that disagree about it.

    A flat bar cannot serve both: 0.40 takes 396 of 400 random movers and 9 of
    40 room evaders, 0.22 takes 294 and 28. The stall trigger is what lets one
    cop do both, and this pins the shape rather than the exact counts — a cop
    that quietly stopped walling would still pass a test that only checked the
    random column, which is how the barrier dial went a week without anyone
    noticing it declined eleven walls of fourteen.
    """
    patient = _captures(lambda: CopBrain(), lambda seed: RandomThief(seed), range(4))
    never = _captures(lambda: CopBrain(stall_patience=99), lambda seed: RandomThief(seed), range(4))

    assert patient >= never, "walling once stalled must not cost us the blunderers"

    walls_on = _captures(lambda: CopBrain(), lambda _s: RoomEvader())
    walls_off = _captures(lambda: CopBrain(stall_patience=99), lambda _s: RoomEvader())

    assert walls_on > walls_off, (
        f"the stall trigger converted {walls_on} evaders against {walls_off} without it"
    )
