"""The seal converts every reacting thief we can build, by co-location only.

This is the cop's whole promise, pinned: Naji's halving plan is a deterministic
win, and nothing else in the cop brain is allowed to block it. It went red in
three different ways before 2026-08-21 and each is a named adversary here:

* the counted #6 windows were won only because the opponents walked into the
  pocket — a refused gate wall left (6,3) open all game (`SideKeeper` exploits
  the side a cut cannot confiscate);
* `lock_cell` without its adjacency requirement sealed rooms we could never
  enter — twelve walls for a `remote seal` the filing layer refuses to claim
  (`RoomEvader` and `GapDancer` both drew exactly that verdict);
* a thief squatting the script's own line postpones every wall the Barrier
  Law protects (`ColumnSquatter` is the informed opponent's version).

**The reason must be a plain capture.** `remote seal (rule 47 only)` is a
bench verdict for a position only a rule-47 implementer concedes; asserting on
`captured` alone would let the plan drift back to manufacturing those.

Runtime is real duels through the live ingress path, about two minutes — the
price of the one gate that guards the match result itself.
"""

import json

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel
from tests.regression.reactive_thieves import (
    ColumnSquatter,
    GapDancer,
    RandomThief,
    RoomEvader,
    SideKeeper,
)


@pytest.fixture
def params() -> GameParams:
    with open("config/game.json") as handle:
        return GameParams.from_config(json.load(handle))


ADVERSARIES = [
    ("our-own-thief", ThiefBrain),
    ("room-evader", RoomEvader),
    ("gap-dancer", GapDancer),
    ("side-keeper", SideKeeper),
    ("column-squatter", ColumnSquatter),
    ("random-fleeing", lambda: RandomThief(1, 0.5)),
    ("random", lambda: RandomThief(4)),
]


@pytest.mark.parametrize("make_thief", [make for _n, make in ADVERSARIES],
                         ids=[name for name, _m in ADVERSARIES])
def test_the_seal_converts_it_inside_the_clock(make_thief, params: GameParams) -> None:
    result = run_cop_duel(SealCop(), [], params, thief_brain=make_thief())

    assert result.captured, (
        f"the plan no longer converts: {result.reason} after "
        f"{len(result.barriers)} walls — a hole is back"
    )
    assert result.reason.startswith("captured"), (
        f"won as `{result.reason}`, which the wire does not pay — "
        "only a co-location claim counts"
    )
    assert result.step <= min(params.survival_threshold, params.max_moves)
