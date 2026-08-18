"""The cop had no strength dial, so every warm-up played our real cop policy.

`ThiefBrain` has sandbagged since the switch existed; `CopBrain` never did. In a
six-sub-game series we hold the cop role three times, so a "sandbagged" warm-up
handed a team we may meet again half our series at full strength — while the
switch that exists to prevent exactly that reported itself as on.

Reduced strength selects a *different policy*, never a withheld input: naive
pursuit, which this brain's own docstring opens by saying "loses to any thief
that simply runs". That is the same standard the thief holds, and the reason
matters — a handicap we invent is not evidence about how we really play, and a
withheld input collapses back onto the full policy whenever the input happens to
be absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.cop_brain import CopBrain

PARAMS = GameParams.from_config({
    "board_and_agents": {"grid_size": 7, "cop_start": [0, 0], "thief_start": [3, 3]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                              "max_moves": 35, "survival_threshold": 35},
})
BOARD = Board(PARAMS)


@dataclass
class _Facts:
    legal: tuple
    belief: dict
    own_position: tuple
    barriers_left: int = 14
    step: int = 5
    sub_game: int = 1
    own_scent: dict | None = None
    scent: dict | None = None


def _facts(position: tuple, belief: dict) -> _Facts:
    return _Facts(legal=legal_moves(BOARD, position), belief=belief, own_position=position)


def _brain(level: str) -> CopBrain:
    return CopBrain(board_supplier=lambda: BOARD, strength=level)


def test_the_dial_exists_at_all() -> None:
    """The regression: `CopBrain` accepted no strength, so config could not reach it."""
    assert _brain("sandbagged").strength == "sandbagged"
    assert CopBrain(board_supplier=lambda: BOARD).strength == "full"


def test_the_two_levels_now_play_the_identical_move() -> None:
    """Sandbagging is retired: the levels differ only in where the report goes.

    It was withdrawn on 2026-08-18 by decision, and the reason is worth keeping.
    A warm-up played at reduced strength measures the reduced agent, so six
    windows of a probe produced one usable data point and a counted series was
    very nearly played by a crippled cop. Hiding strategy from an opponent is
    worth much less than seeing our own defects early.

    So `AT_FULL_STRENGTH` contains every level and this pins the consequence
    across the same 49 position/peak pairs the old assertion used.
    """
    positions = [(0, 0), (3, 0), (6, 6), (0, 6), (2, 2), (1, 4), (5, 1), (3, 3), (6, 0), (0, 3)]
    peaks = [(4, 4), (3, 6), (2, 1), (5, 2), (6, 0)]
    for position in positions:
        for peak in peaks:
            if position == peak:
                continue
            belief = {cell: max(0.001, 0.5 / (1 + 2 * max(abs(cell[0] - peak[0]),
                                                          abs(cell[1] - peak[1]))))
                      for cell in BOARD.cells()}
            facts = _facts(position, belief)
            assert _brain("full").pick_move(facts) == _brain("sandbagged").pick_move(facts)


def test_both_levels_claim_on_the_same_evidence() -> None:
    """The claim bar no longer moves with the level either.

    A claim is the only capture most opponents honour, so a differing bar was
    where the weakening actually lived. With sandbagging retired the two must
    agree, or a friendly would still be measuring a different agent from the one
    that plays the counted series.
    """
    full, weak = _brain("full"), _brain("sandbagged")

    assert weak._claim_bar() == full._claim_bar()

def test_reduced_strength_lays_no_barriers() -> None:
    """The dial that decides matches: 0.05 captured 4% of games, 0.40 captured 100%.

    A reduced cop that still laid optimal traps would be sandbagged in name only.
    """
    belief = {(4, 4): 0.9}
    for cell in BOARD.cells():
        belief.setdefault(cell, 0.001)
    facts = _facts((0, 0), belief)

    assert _brain("sandbagged").pick_barrier(facts) is None


def test_reduced_strength_can_still_capture() -> None:
    """A cop that can never win is a forfeit dressed as a handicap.

    The claim is the only capture most opponents honour, so the capture step
    stays available at every level; what weakens is how we close the distance.
    """
    origin = (3, 3)
    landing = (3, 4)
    belief = {landing: 0.9}
    facts = _facts(origin, belief)

    assert _brain("sandbagged").pick_move(facts) == Move.EAST


def test_naive_pursuit_actually_walks_toward_the_peak() -> None:
    """It must be real play, not noise: the weak policy still closes distance."""
    belief = {(6, 6): 0.5}
    for cell in BOARD.cells():
        belief.setdefault(cell, 0.001)

    move = _brain("sandbagged").pick_move(_facts((0, 0), belief))

    assert move in (Move.SOUTH, Move.EAST), f"pursuit should close on (6,6), got {move}"


def test_the_factory_hands_the_cop_its_level(monkeypatch) -> None:
    """Wired, not merely declared — the thief's dial sat unread for weeks.

    `brain_factory` passes `strength` to any brain that declares the field, so
    adding it to `CopBrain` is enough — but "is enough" is exactly the claim
    that was wrong last time, so it is checked rather than reasoned about.
    """
    from najamjad_agent.constants import Role
    from najamjad_agent.sdk.match_setup import brain_factory

    class _Manager:
        def get(self, key: str, default: Any = None) -> Any:
            return "sandbagged" if key == "strength.level" else default

    class _State:
        board = BOARD

    built = brain_factory(_Manager())(Role.COP, _State())

    assert getattr(built, "strength", "full") == "sandbagged"
