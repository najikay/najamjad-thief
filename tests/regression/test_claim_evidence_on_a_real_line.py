"""The measurement that settled the capture-claim question, pinned as a gate.

Three sessions argued about whether a capture claim should reach the belief, and
two of them removed the wiring on the strength of a scenario nobody had replayed
against a real opponent. This file replays one: uoh-ay26's g03 from 2026-08-08,
their cells and their declarations, taken from the records they revealed at the
audit and left on the steps they were declared on.

It is the right line to gate on because they are the hardest honest case in the
archive — 34 claims, nine walls, **no scent at all**, and hints that parse to
nothing. Their claims are the only position signal in the game, and reading them
is the difference between losing the mini-game and never being touched.

Both directions are asserted. A gate that only checked the fixed behaviour would
pass just as happily against a thief that is good for some unrelated reason, and
this repo has shipped exactly that mistake before: an earlier version of the
silent-opponent gate passed with the entire fix disabled.
"""

from __future__ import annotations

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.scripted_opponents import (
    UOH_AY26_G03_BARRIERS,
    UOH_AY26_G03_SWEEP,
)
from tests.regression.silent_peer import SilentPeerBelief

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


def _play(params: GameParams, deaf: bool = False) -> tuple:
    """Their line, with the belief our thief genuinely holds against it."""
    belief = SilentPeerBelief(params, UOH_AY26_G03_SWEEP, UOH_AY26_G03_BARRIERS)
    if deaf:
        # The counterfactual: their walls still arrive, their claims do not.
        walls = dict(UOH_AY26_G03_BARRIERS)
        belief._message = lambda cop, step: {  # noqa: SLF001
            "step": step,
            "commit": f"{step:064x}",
            **({"barrier_placed": list(walls[step])} if step in walls else {}),
        }
    result = run_duel(
        ThiefBrain(), UOH_AY26_G03_SWEEP, params, UOH_AY26_G03_BARRIERS, belief_for=belief
    )
    return result, belief


def test_the_thief_survives_the_line_that_used_to_catch_it(params: GameParams) -> None:
    """The headline. Claims ignored, they had us at step 26."""
    result, _ = _play(params)

    assert result.survived, f"captured at step {result.steps_survived}: {result.reason}"
    assert result.steps_survived == 35


def test_ignoring_their_claims_costs_us_the_belief_even_when_we_survive(
    params: GameParams,
) -> None:
    """The counterfactual, updated the day the thief outgrew it.

    Stripping the claims used to lose this mini-game outright, at step 26. It no
    longer does: `thief_safety.LOCAL_ROOM_RADIUS` keeps the thief out of the
    corner the tie-breaker used to pick, and it survives the line blind. That is
    the thief improving, not the claim wiring becoming pointless — so the
    counterfactual now asserts what it still costs, which is the belief.

    Reading their claims puts the peak on the cop's exact cell every turn;
    ignoring them leaves it wrong by roughly two cells. Against a cop that does
    close, that difference is the game, which is why the wiring stays.
    """
    def located(deaf: bool) -> int:
        """Turns on which the belief named their true cell, claims on or off."""
        belief = SilentPeerBelief(params, UOH_AY26_G03_SWEEP, UOH_AY26_G03_BARRIERS)
        if deaf:
            walls = dict(UOH_AY26_G03_BARRIERS)
            belief._message = lambda cop, step: {  # noqa: SLF001
                "step": step, "commit": f"{step:064x}",
                **({"barrier_placed": list(walls[step])} if step in walls else {}),
            }
        hits = 0
        for step, cop in enumerate(UOH_AY26_G03_SWEEP, start=1):
            belief(cop, step, (3, 3))
            hits += belief.peak == cop
        return hits

    heard, deaf = located(deaf=False), located(deaf=True)

    assert heard >= 30, f"reading their claims located them on only {heard} of 34 turns"
    assert deaf <= 5, f"ignoring their claims still located them on {deaf} turns"
    assert heard > deaf * 4, "the claim wiring must be the reason we know where they are"


def test_their_claims_put_the_belief_on_the_cop_every_single_turn(
    params: GameParams,
) -> None:
    """Not merely "better" — exact on every turn it can be, against a silent peer.

    Asserted on the belief rather than on survival because that is the thing the
    wiring changes; survival is downstream of it and can move for other reasons.

    The thief is held at its start cell so the cop line stays the archived one,
    which means their sweep walks over us on three of the thirty-four steps. On
    those the claim names our own square and is dropped by design — in a real
    game it would be a capture and there would be no next turn to hold a belief
    for. They are excluded rather than tolerated, so a regression that started
    dropping *other* claims could not hide inside a slack threshold.
    """
    belief = SilentPeerBelief(params, UOH_AY26_G03_SWEEP, UOH_AY26_G03_BARRIERS)

    exact = checkable = 0
    for step, cop in enumerate(UOH_AY26_G03_SWEEP, start=1):
        belief(cop, step, (3, 3))
        if cop == (3, 3):
            continue
        checkable += 1
        exact += belief.peak == cop

    assert checkable == 31
    assert exact == checkable, (
        f"the belief named their exact cell on {exact} of {checkable} turns"
    )
