"""The line that actually beat us, replayed — not a synthetic sweep.

2026-08-06, practice series against Amjad, mini-game 2. Our thief walked to
[5,5], **stood still for five consecutive turns** while the cop closed from
distance 6 to 2, was herded west along row 6, and died in the corner at [6,0]
where both exits were covered from [5,1]. Captured at step 20.

Every offline arena we had passed that policy. They could not have caught it:
they exercised the *blind* path, and against a peer who emits scent the belief
is informative, so `thief_safety.choose` runs instead. This file exists so the
one line we have real evidence for is measured on every run.

Why it stood still: on an intact board both room keys in `rank` are pinned at
the component size, so the ranking collapses to escape routes and then
distance — and an unbounded exit count outranks any amount of distance. From
[5,5] against a cop at [3,2], STAY had four exits and distance 5; moving away
had three exits and distance 6. STAY won, and kept winning.
"""

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.scripted_opponents import AMJAD_G02_BARRIERS, AMJAD_G02_SWEEP

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


def _replay(params: GameParams):
    return run_duel(ThiefBrain(), AMJAD_G02_SWEEP, params, AMJAD_G02_BARRIERS)


def test_standing_still_never_outranks_backing_away(params: GameParams) -> None:
    """The defect at the level it actually lives, from the real position.

    Asserted on the *ranking* rather than on an outcome, because the outcome
    cannot be reproduced offline: `run_duel` hands the thief the cop's exact
    cell, and under perfect information the unfixed policy survives this line
    too. A survival assertion here passes with the fix reverted — it measures
    nothing. This one fails.

    [5,5] against a cop at [3,2] is the exact position from the sealed log where
    the freeze began. STAY held four exits and distance 5; moving away held
    three exits and distance 6. Exits ranked above distance and were unbounded,
    so STAY won — and kept winning for five turns while the cop walked in.
    """
    from najamjad_agent.constants import Move
    from najamjad_agent.domain.board import Board
    from najamjad_agent.strategy.thief_safety import choose

    board = Board(params)
    tied = choose(board, (5, 5), (3, 2), tuple(Move))

    assert Move.STAY not in tied, "chose to stand still while the cop closed"
    assert tied, "a safe move existed and none was offered"


def test_the_thief_does_not_idle_while_the_cop_closes(params: GameParams) -> None:
    """The mechanism, pinned separately from the outcome.

    Surviving could happen for the wrong reason — a line that never reaches us
    survives whatever we do. What must not recur is standing still *while the
    distance shrinks*, which is what gave the cop four free squares.
    """
    result = _replay(params)
    cop = dict(enumerate(AMJAD_G02_SWEEP, start=1))

    idled_while_closing = 0
    for step, (before, after) in enumerate(zip(result.path, result.path[1:], strict=False), start=1):
        here, next_cop = cop.get(step), cop.get(step + 1)
        if before != after or here is None or next_cop is None:
            continue
        was = abs(before[0] - here[0]) + abs(before[1] - here[1])
        now = abs(after[0] - next_cop[0]) + abs(after[1] - next_cop[1])
        if now < was:
            idled_while_closing += 1

    assert idled_while_closing <= 2, (
        f"stood still through {idled_while_closing} turns of the cop closing; "
        "the real game did this five times in a row at [5,5]"
    )
