"""Our thief against sealing cops of several qualities (T-2718).

`test_thief_survives_vibecode` replays archived cop lines, which do not react,
and `cop_duel` with a live `SealCop` covers exactly one sealer — the good one.
Neither answers the question Naji asked on 2026-08-18: does the thief handle a
*worse* sealer, and does it handle cops that wall versus cops that do not?

It is a fair question, because the failure this suite was written after was
depth, not tactics. `wall_safety.survives_one_wall` looks exactly **one barrier**
ahead, so a cop building a multi-wall trap is invisible to it until the last
brick — and the thief's first loss to a sealer came from ranking that one-ply
verdict above simple adjacency.

The degradations are the sealer's own historical bugs, each of which cost us a
game before it was a rule, so this is a suite of opponents we have actually met.
"""

import json
import random

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.seal_cop import CUT, SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel


class NearGate(SealCop):
    """Gate at the end *nearest* the thief, so it can slip round the build."""

    def _commit(self, board, thief):  # type: ignore[no-untyped-def]
        if self.gate is not None:
            return
        self.lane = CUT - (1 if thief[1] > CUT else -1)
        self.gate = (0, CUT) if thief[0] <= CUT else (board.size - 1, CUT)


class Rechooser(SealCop):
    """Re-picks the cut row every turn: two half-cuts that seal nothing."""

    def _row_cells(self, board, here, thief):  # type: ignore[no-untyped-def]
        self.row = None
        return super()._row_cells(board, here, thief)


class Impatient(SealCop):
    """Abandons the seal with the quota nearly full and reverts to chasing."""

    def _settled(self, board, thief, left):  # type: ignore[no-untyped-def]
        return left <= 11


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
    [SealCop, NearGate, Rechooser, Impatient, CopBrain, RandomCop],
    ids=["seal-full", "seal-near-gate", "seal-rechooses-row",
         "seal-gives-up", "pursuit-and-walls", "random"],
)
def test_the_thief_survives_every_grade_of_sealer(make_cop, params: GameParams) -> None:
    """Survival to the horizon is the thief's win condition; nothing less counts."""
    result = run_cop_duel(make_cop(), [], params, thief_brain=ThiefBrain())

    assert not result.captured, (
        f"{make_cop.__name__} took us on step {result.step} "
        f"after {len(result.barriers)} barriers"
    )
    assert result.step == min(params.survival_threshold, params.max_moves)
