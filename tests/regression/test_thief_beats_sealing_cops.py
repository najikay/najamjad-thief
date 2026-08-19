"""Our thief against sealing cops of several qualities (T-2718).

Written 2026-08-18 asserting the thief survives every grade of sealer, which was
true of the sealer that existed that day. It is not true of the one Naji
dictated on 2026-08-19: that cop halves the board, halves the half, and takes us
on step 29 for ten barriers. The assertion has therefore been **inverted rather
than deleted** — the fact it now records is a defeat, and a suite that quietly
dropped it would be the second time this repo answered a failing benchmark by
removing the assertion instead of the assumption.

The measurement that matters is which grade is fatal, and it is not the one we
guessed. A sealer that halves the board and stops is survivable (35 steps, six
barriers spent); a sealer that leaves its gate unwalled still takes us on 29.
**The second cut is the whole game.** Once the 3x3 closes, `domain/endgame.py`
prices it a forced cop win on a single barrier — there is no thief play inside
it, so no amount of thief work turns that column green. The thief's only counter
is to be on the far side before the cut completes, which is a different fix from
anything this file can assert.

The old degradations are gone because they had stopped degrading anything:
`NearGate`, `Rechooser` and `Impatient` overrode `_commit`, `_row_cells` and
`_settled`, none of which survived the rewrite to an explicit script. All three
were plain `SealCop` wearing a different name, and the suite had been grading one
cop four times while reporting four grades. A dead override is worse than no
override, because it claims a coverage it does not have. The two below are
written against the members the current cop actually has.
"""

import json
import random

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel

#: Steps the thief reaches against a sealer that finishes its plan, measured
#: 2026-08-19. A ratchet, not a target: lasting *fewer* steps is a real thief
#: regression and fails here, while lasting more is an improvement the pin is
#: raised to meet.
HELD_AGAINST_A_FINISHED_SEAL = 29
#: Barriers that cop had to spend to do it. If a future cop takes us for less,
#: the seal got cheaper and this file should say so out loud.
COST_OF_TAKING_US = 10


class GivesUp(SealCop):
    """Halves the board and stops: never builds the second cut.

    The survivable grade, and the one that tells us where the danger is.
    """

    def _refill(self, board, thief, here):  # type: ignore[no-untyped-def]
        super()._refill(board, thief, here)
        if self.phase == "row":
            self.script = []


class GateLeftOpen(SealCop):
    """Walks the whole plan but never walls a gate behind itself."""

    def _gate_script(self, thief):  # type: ignore[no-untyped-def]
        return [(stand, None) for stand, _wall in super()._gate_script(thief)]


class RandomCop(CopBrain):
    """No plan at all — the control, and the only one that may wall nothing."""

    def __init__(self, seed: int = 7, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self._rng = random.Random(seed)

    def pick_barrier(self, facts):  # type: ignore[no-untyped-def]
        return super().pick_barrier(facts) if self._rng.random() < 0.3 else None

    def pick_move(self, facts):  # type: ignore[no-untyped-def]
        return self._rng.choice(list(facts.legal))


@pytest.fixture
def params() -> GameParams:
    with open("config/game.json") as handle:
        return GameParams.from_config(json.load(handle))


@pytest.mark.parametrize(
    "make_cop",
    [GivesUp, CopBrain, RandomCop],
    ids=["seal-gives-up", "pursuit-and-walls", "random"],
)
def test_the_thief_survives_every_cop_that_does_not_finish_a_seal(
    make_cop, params: GameParams
) -> None:
    """Survival to the horizon is the thief's win condition; nothing less counts."""
    result = run_cop_duel(make_cop(), [], params, thief_brain=ThiefBrain())

    assert not result.captured, (
        f"{make_cop.__name__} took us on step {result.step} "
        f"after {len(result.barriers)} barriers"
    )
    assert result.step == min(params.survival_threshold, params.max_moves)


@pytest.mark.parametrize(
    "make_cop", [SealCop, GateLeftOpen], ids=["seal-full", "seal-gate-open"]
)
def test_a_finished_seal_takes_us_and_we_record_how_dearly(
    make_cop, params: GameParams
) -> None:
    """The defeat, pinned in both directions.

    Not `not captured`: that assertion is false and the honest form of a false
    assertion is the true one beside it. Losing *sooner* is a thief regression;
    being taken for *fewer* barriers means the seal got cheaper. Either is worth
    a red build, and a thief that escapes outright fails the pin too — which is
    the failure we would most like to be handed.
    """
    result = run_cop_duel(make_cop(), [], params, thief_brain=ThiefBrain())

    assert result.step >= HELD_AGAINST_A_FINISHED_SEAL, (
        f"the thief now falls on step {result.step}, sooner than the "
        f"{HELD_AGAINST_A_FINISHED_SEAL} it held on 2026-08-19"
    )
    if result.captured:
        assert len(result.barriers) >= COST_OF_TAKING_US, (
            f"the seal got cheaper: {len(result.barriers)} barriers, "
            f"not the {COST_OF_TAKING_US} it used to cost"
        )
