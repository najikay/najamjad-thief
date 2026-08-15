"""The line that took three counted mini-games off us, and the key that answers it.

vibecode's cop, move for move from the 2026-08-14 counted g02: walk straight in,
and once at distance two spend barriers on the thief's exits rather than on its
cell. Two walls — `(6,4)` then `(6,5)` — and a step onto `(6,6)`.

**Survival depended on the sub-game number**, which is the part worth keeping.
Sub-games 1, 3, 4 and 6 survived; **2 and 5 were caught at step 13, both ending
on (6,6)**. We play thief in the even sub-games, and the counted series lost all
three of them. `_break_tie` exists so a scripted opponent cannot solve one line
by replaying it — but it was choosing among moves the ranking had wrongly called
equal, and two of its six choices walked into a corner.

The keys above it all tie on an intact board: component size is identical across
one component and the exit count saturates at three. `LOCAL_ROOM_RADIUS` breaks
that tie with the quantity barriers actually attack — a corner reaches six cells
in two steps, a central cell thirteen.
"""

from __future__ import annotations

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.silent_peer import SilentPeerBelief

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
    },
}

#: Their cop's true cells, steps 1-14, from their revealed records.
VIBECODE_COP = (
    (1, 0), (2, 0), (3, 0), (3, 1), (4, 1), (4, 2), (4, 3),
    (4, 4), (5, 4), (5, 4), (5, 5), (5, 5), (5, 6), (6, 6),
)
#: The two walls that sealed the corner, on the steps they were declared.
VIBECODE_WALLS = {10: (6, 4), 12: (6, 5)}


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


class _InSubGame:
    """Our thief, playing as a given sub-game number.

    The number reaches `_break_tie` and nothing else, which is exactly the point:
    it must not decide whether we live.
    """

    def __init__(self, number: int) -> None:
        self.number, self.brain = number, ThiefBrain()

    def pick_move(self, facts):
        facts.sub_game = self.number
        return self.brain.pick_move(facts)


@pytest.mark.parametrize("sub_game", [1, 2, 3, 4, 5, 6])
def test_every_sub_game_survives_the_line_that_beat_us(params: GameParams, sub_game: int) -> None:
    """2 and 5 were caught at step 13 before `LOCAL_ROOM_RADIUS` existed."""
    belief = SilentPeerBelief(params, VIBECODE_COP, VIBECODE_WALLS)
    result = run_duel(
        _InSubGame(sub_game), VIBECODE_COP, params, VIBECODE_WALLS, belief_for=belief
    )

    assert result.survived, (
        f"sub-game {sub_game} caught at step {result.steps_survived}, "
        f"ending on {result.path[-1]}"
    )


def test_survival_does_not_depend_on_which_sub_game_it_is(params: GameParams) -> None:
    """The tie-break may vary the *line*; it must never vary the *outcome*.

    Asserted separately from the cases above because it is the real invariant.
    Six identical passes could also mean the variation stopped working, so
    `test_the_six_sub_games_of_a_series_do_not_play_one_line` guards the other
    side of it — the lines must still differ.
    """
    outcomes = set()
    for number in range(1, 7):
        belief = SilentPeerBelief(params, VIBECODE_COP, VIBECODE_WALLS)
        outcomes.add(
            run_duel(
                _InSubGame(number), VIBECODE_COP, params, VIBECODE_WALLS, belief_for=belief
            ).survived
        )

    assert outcomes == {True}
