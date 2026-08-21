"""Counted #6, g01/g03/g05: the corner hunt that took our thief three times.

All three windows were byte-identical — our deterministic thief replayed the
same losing line, and their cop replayed the same kill. Their cop had placed
**zero** walls when our own `sealing_cells` "stand in the gap" preference
marched us [5,6] -> [6,6] into the corner at step 10, overriding the seal-cost
floor that runs after it; one wall at [6,5] and a zugzwang STAY later we were
taken on [5,6] at step 13. The fence counter, firing with no fence anywhere on
the board, was the whole death.

Two pins, because a scripted line and a reacting policy answer different
questions. The replay is the exact archived geometry (their cop cells as our
thief saw them each decision, the wall arriving before our step-12 move); the
`CornerHunter` family is the policy that produced it, in all twenty-four
pursuit tie-breaks, so the fix cannot be an overfit to one line.
"""

import json
from itertools import permutations

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.reactive_cops import CornerHunter, duel_react

#: Their cop's cell at each of our decision steps 1..13 — position after their
#: previous move, read from the sealed records of g01 (g03 and g05 identical).
AHK_YOSI_LINE = (
    (0, 0), (0, 1), (1, 1), (2, 1), (2, 2), (2, 3), (3, 3),
    (4, 3), (4, 4), (4, 5), (5, 5), (5, 5), (5, 6),
)
#: Their single barrier, on the board before our step-12 decision.
AHK_YOSI_WALL = {12: (6, 5)}


@pytest.fixture
def params() -> GameParams:
    with open("config/game.json") as handle:
        return GameParams.from_config(json.load(handle))


def test_the_archived_kill_line_no_longer_kills(params: GameParams) -> None:
    result = run_duel(ThiefBrain(), AHK_YOSI_LINE, params, barriers=AHK_YOSI_WALL)

    assert result.survived, (
        f"caught again at step {result.steps_survived} ({result.reason}) — "
        "the intact-board gap preference is back"
    )


@pytest.mark.parametrize(
    "tie",
    list(permutations((Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST))),
    ids=lambda tie: "/".join(move.name[0] for move in tie),
)
def test_the_reacting_hunter_family_never_takes_us(tie, params: GameParams) -> None:
    steps, captured, reason = duel_react(ThiefBrain(), CornerHunter(tie), params)

    assert not captured, f"hunter {tie} took us at step {steps} ({reason})"
