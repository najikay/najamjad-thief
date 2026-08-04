"""The gate for the failure that actually lost the series: a peer who says nothing.

`test_uoh_sqak_sweep.py` replays their line while handing our thief the cop's
exact cell, which answers "is our move policy sound" — and it is. This file
answers the question that was never asked, and whose answer was no.

uoh-sqak send **no scent, no hints and no observations**. Our belief therefore
stayed uniform for the entire mini-game; `thief_brain._cop_cell` correctly
declined to name a cell from a flat distribution; and the thief fell through to
the weighted-sum policy that had already lost three games. The exact solve and
the distance-2 invariant — the two pieces of work that make our thief good —
never executed against them at all.

The archived sealed records show what that looked like. Across g02, g04 and g06
our thief occupied **four distinct cells in eleven steps**, held (5,5) for six
consecutive turns, and played a near-identical line in all three games. It was
not evading; it was standing still while being swept.

What they cannot withhold is what the rules make mandatory: a capture claim
names the cop's own cell (rules 21-22), and a barrier declaration puts the cop
in a five-cell set and says it did not move (rules 15-16). There were 289 such
disclosures in the series we lost. These tests assert we now read them.
"""

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel
from tests.regression.scripted_opponents import UOH_SQAK_BARRIERS, UOH_SQAK_SWEEP
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

#: Survival against a silent opponent, which is the number the league pays for:
#: 10 points a game instead of 5. Lower it only deliberately.
SILENT_BEST_STEPS = 35


@pytest.fixture()
def params() -> GameParams:
    return GameParams.from_config(CONFIG)


def silent_duel(params: GameParams, brain=None):
    """Their sweep, with the belief our agent would genuinely hold against it."""
    belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, UOH_SQAK_BARRIERS)
    result = run_duel(
        brain or ThiefBrain(), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS, belief_for=belief
    )
    return result, belief


def test_the_thief_survives_a_peer_that_transmits_nothing(params: GameParams) -> None:
    """The whole point. No scent, no hints — and the thief still lasts the game."""
    result, _ = silent_duel(params)

    assert result.survived
    assert result.steps_survived == SILENT_BEST_STEPS


def test_survival_against_silence_does_not_regress(params: GameParams) -> None:
    """The ratchet, on the axis that was costing us roughly 30 points a series."""
    result, _ = silent_duel(params)

    assert result.steps_survived >= SILENT_BEST_STEPS


def test_a_capture_claim_localises_the_cop_exactly(params: GameParams) -> None:
    """A claim names the cop's own cell, so the belief should peak on it.

    `evaluate_capture` scores a capture only when the cop occupies the cell it
    claims, which is what makes a claim an exact fix rather than a hint.
    """
    belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, barriers=())

    for step, cop in enumerate(UOH_SQAK_SWEEP[:6], start=1):
        belief(cop, step, (3, 3))
        assert belief.peak == cop, f"step {step}: belief peaked at {belief.peak}, cop at {cop}"


def test_the_evidence_path_actually_runs(params: GameParams) -> None:
    """Guard against the endemic failure here: a component with no caller.

    Seven finished-but-unreferenced components have been found in this repo.
    This asserts the sighting is not the eighth.
    """
    _, belief = silent_duel(params)

    assert "cop.sighted" in belief.events


def test_the_belief_stays_flat_when_the_declarations_are_ignored(params: GameParams) -> None:
    """The instrument must still be able to fail, or it is measuring nothing.

    Strips the two mandatory declarations out of the peer's messages, leaving
    the genuinely-silent peer we used to face. The belief must then be too flat
    for `_cop_cell` to name a cell from — which is the state the thief was in
    for every one of the six games.

    Asserted on the *decision* rather than on the spread. The distribution is
    not perfectly uniform even with no evidence at all, because excluding our
    own square each turn and re-diffusing dents it slightly; that dent is real
    and harmless, and a test that forbade it would be measuring arithmetic
    rather than behaviour. What matters is that nothing in it clears the
    confidence floor.
    """
    belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, barriers=())
    belief._message = lambda cop, step: {"step": step, "commit": f"{step:064x}"}  # noqa: SLF001

    for step, cop in enumerate(UOH_SQAK_SWEEP[:6], start=1):
        distribution = belief(cop, step, (3, 3))

    assert ThiefBrain()._cop_cell(distribution) is None  # noqa: SLF001
    assert belief.peak != UOH_SQAK_SWEEP[5], "a silent peer must not be locatable"


def test_the_blind_thief_still_loses_the_way_the_archive_recorded(params: GameParams) -> None:
    """Pin the original failure so the gate keeps its teeth.

    With the belief forced flat the thief is back on the weighted sum, and the
    archived behaviour was near-total immobility: four distinct cells in eleven
    steps across three games. Assert the immobility, not a step count, because
    immobility is the diagnosis.
    """

    class Blind:
        def __init__(self) -> None:
            self._inner = ThiefBrain()

        def pick_move(self, facts):
            facts.belief = {}
            return self._inner.pick_move(facts)

    result = run_duel(Blind(), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS)

    assert len(set(result.path[:12])) <= 5, (
        "the blind policy used to visit four cells in eleven steps; "
        f"this replay visited {len(set(result.path[:12]))}"
    )


def test_a_barrier_narrows_the_cop_to_its_reach_without_naming_one_cell(
    params: GameParams,
) -> None:
    """A barrier is a five-cell fix, and must not be reported as certainty.

    The Barrier Law admits the cop's own cell or one orthogonal step, so a
    declaration that produced a single confident cell would be claiming to know
    something the rules do not tell us.
    """
    from najamjad_agent.domain.board import Board
    from najamjad_agent.domain.cop_sighting import from_barrier

    board = Board(params).with_barrier((3, 3))
    sighting = from_barrier(board, (3, 3), step=4)

    assert sighting is not None
    assert not sighting.exact
    assert set(sighting.cells) == {(2, 3), (4, 3), (3, 2), (3, 4)}
