"""Our thief against our own sealer stack, in every grade it comes in (T-2718).

The history of this file is the history of the arms race, and the assertions
have changed sides twice. Written 2026-08-18 asserting the thief survives every
grade of sealer, which was true of the sealer that existed that day. Inverted
on 2026-08-19 when the scripted sealer took us on 29 — recorded as a defeat
rather than deleted. Rewritten 2026-08-21, because that day's cop work closed
the holes the "survivable grades" were survivable through: the gate at (6,3)
is re-taken instead of abandoned when its wall is refused, `lock_cell` demands
adjacency, and the pocket solver prices wins to co-location. With those fixed,
even the crippled mutants convert — `GivesUp` never builds the second cut and
still wins at 32, because a properly sealed 3-wide half is a forced capture by
the same table the seal is budgeted against, and the shared lock-and-solve
core finishes it without a script.

So the file now records the honest asymmetry:

* **Every grade of the sealer stack takes our thief.** Not a thief failure to
  fix: no opponent in this league runs this stack, our thief survives every
  archived opponent line and 24 reacting corner-hunter variants
  (`test_ahk_yosi_corner_hunt.py`), and the losing side of a solved position
  is the wrong place to spend strategy work. The ratchet guards the *steps*:
  falling below 29 is a real thief regression.
* **A cop without the halving plan still takes nothing.** Pursuit-and-walls
  and the random control must never capture — that is the theorem the safety
  rule implements, and it is the pin that catches a thief blunder fastest.
"""

import json
import random

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel

#: Steps the thief reaches against the sealer stack. A ratchet, not a target:
#: lasting *fewer* steps is a real thief regression and fails here, while
#: lasting more is an improvement the pin is raised to meet. 29 is the
#: 2026-08-21 floor across all three grades (GateLeftOpen is the fastest).
HELD_AGAINST_THE_SEAL = 29
#: Barriers the cheapest conversion spends. If a future cop takes us for
#: less, the seal got cheaper and this file should say so out loud.
COST_OF_TAKING_US = 9


class GivesUp(SealCop):
    """Halves the board and stops: never builds the second cut.

    Survivable until 2026-08-21; converting now is the proof that the halves
    it seals are themselves lost ground — 3 cells wide, which the forced-win
    table prices as a capture for the lock-and-solve core it still carries.
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
    "make_cop", [CopBrain, RandomCop], ids=["pursuit-and-walls", "random"]
)
def test_the_thief_survives_every_cop_without_the_halving_plan(
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
    "make_cop",
    [SealCop, GateLeftOpen, GivesUp],
    ids=["seal-full", "seal-gate-open", "seal-gives-up"],
)
def test_every_grade_of_the_seal_takes_us_and_we_record_how_dearly(
    make_cop, params: GameParams
) -> None:
    """The defeat, pinned in all three directions.

    Losing *sooner* than the floor is a thief regression; being taken for
    fewer barriers means the seal got cheaper; and a capture reported any
    other way than co-location would be a wire the filing layer cannot cash
    (`remote seal` is a bench verdict, not a win). A thief that escapes a
    grade outright fails the pin too — which is the failure we would most
    like to be handed, since it means the plan grew a hole.
    """
    result = run_cop_duel(make_cop(), [], params, thief_brain=ThiefBrain())

    assert result.captured, (
        f"{make_cop.__name__} no longer converts: {result.reason} — "
        "either the thief found a hole (raise these pins to celebrate) or "
        "the plan lost one of its 2026-08-21 fixes"
    )
    assert result.reason.startswith("captured"), result.reason
    assert result.step >= HELD_AGAINST_THE_SEAL, (
        f"the thief now falls on step {result.step}, sooner than the "
        f"{HELD_AGAINST_THE_SEAL} it held on 2026-08-21"
    )
    assert len(result.barriers) >= COST_OF_TAKING_US, (
        f"the seal got cheaper: {len(result.barriers)} barriers, "
        f"not the {COST_OF_TAKING_US} it used to cost"
    )
