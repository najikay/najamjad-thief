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


def test_the_two_levels_sometimes_choose_different_moves() -> None:
    """Interception cuts the angle; naive pursuit walks at the peak.

    Deliberately a weak assertion, because the truth is weak: measured across 49
    position/peak pairs on a diffused belief, the two policies pick a different
    move only 3 times. On a 7x7 board every sane pursuit walks toward the peak,
    so movement is simply not where a cop can hide its strength — which is why
    the barrier and claim behaviour below carry the weakening, and why a dial
    that only changed movement would be sandbagging in name.
    """
    positions = [(0, 0), (3, 0), (6, 6), (0, 6), (2, 2), (1, 4), (5, 1), (3, 3), (6, 0), (0, 3)]
    peaks = [(4, 4), (3, 6), (2, 1), (5, 2), (6, 0)]
    differences = 0
    for position in positions:
        for peak in peaks:
            if position == peak:
                continue
            belief = {cell: max(0.001, 0.5 / (1 + 2 * max(abs(cell[0] - peak[0]),
                                                          abs(cell[1] - peak[1]))))
                      for cell in BOARD.cells()}
            facts = _facts(position, belief)
            differences += (
                _brain("full").pick_move(facts) != _brain("sandbagged").pick_move(facts)
            )

    assert differences >= 1, "the two levels are move-for-move identical everywhere"


def test_reduced_strength_demands_more_before_it_claims() -> None:
    """Where the weakening actually lives, with barriers.

    A claim is the only capture most opponents honour, so a cop that waits for
    near-certainty captures less — which is what weaker has to mean.
    """
    full, weak = _brain("full"), _brain("sandbagged")

    assert weak._claim_bar() > full._claim_bar()

    # A cell the full cop treats as claimable and the reduced one does not.
    # Asserted on the claim decision rather than the move: naive pursuit walks
    # toward the peak anyway, so the two agree on direction while disagreeing
    # about whether they are committing to a capture — which is the thing that
    # actually decides the game.
    belief = {(3, 4): full.claim_threshold * 1.5}
    facts = _facts((3, 3), belief)

    assert full.capture_step_available(facts) is True
    assert weak.capture_step_available(facts) is False, "reduced strength claimed a marginal cell"


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
