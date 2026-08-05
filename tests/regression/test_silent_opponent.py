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


def test_a_capture_claim_is_not_treated_as_a_cop_position_fix(params: GameParams) -> None:
    """The regression that reading it as one caused, pinned so it cannot return.

    `capture.answer_capture_claim(true_thief_cell, claimed_cell)` settles the
    semantics from our own code: a claim names the cell where the cop asserts
    *the thief* is. That equals the cop's own cell only for a claim that lands.
    uoh-sqak happened to claim only their own cell, which is the sole reason
    believing it looked correct against their recorded line.

    Measured before this was removed: against a cop claiming one row off the
    thief went from 35/35 to captured at step 13; against one claiming our own
    cell it was blinded every turn, because 0.99 of the mass landed on our
    square and the very next `exclude()` deleted it. Both were worse than
    ignoring claims outright.
    """
    belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, barriers=())

    for step, cop in enumerate(UOH_SQAK_SWEEP[:4], start=1):
        distribution = belief(cop, step, (3, 3))

    assert ThiefBrain()._cop_cell(distribution) is None, (  # noqa: SLF001
        "claims alone must not produce a confident cop cell"
    )


def test_a_claim_on_our_own_cell_cannot_blind_us(params: GameParams) -> None:
    """The free attack: claim where we stand, every turn, and watch us go flat.

    Believing the claim put near-certainty on our own square; `exclude()` then
    zeroed it, `normalise` spread the residue, and the belief was uniform again
    on every single turn. The opponent needs no information to do this — our own
    scent field hands them our exact cell for free.
    """
    belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, UOH_SQAK_BARRIERS)
    belief._message = lambda cop, step: {  # noqa: SLF001
        "step": step,
        "commit": f"{step:064x}",
        "capture_claim": [3, 3],
    }

    for step, cop in enumerate(UOH_SQAK_SWEEP[:5], start=1):
        belief(cop, step, (3, 3))

    assert belief.peak != (3, 3), "a claim on our own cell must not become the belief peak"


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


class Blind:
    """Our thief with the belief forced flat — the silent-peer case, exactly."""

    def __init__(self) -> None:
        self._inner = ThiefBrain()

    def pick_move(self, facts):
        facts.belief = {}
        return self._inner.pick_move(facts)


def test_the_blind_thief_does_not_stand_still(params: GameParams) -> None:
    """The regression that lost three archived mini-games, pinned inverted.

    The archive recorded near-total immobility: four distinct cells in eleven
    steps, (5,5) held for six consecutive turns, a near-identical line in all
    three games. It was never a preference for standing still — the fallback
    read a *flat* belief as if it named a direction, ran to the corner furthest
    from a cop that did not exist, and then found nothing left to improve.

    Asserted on distinct cells rather than a step count, because immobility is
    the diagnosis and a step count would pass for a thief that froze somewhere
    the sweep happens not to reach. That is not a hypothetical: an earlier
    version of this gate did exactly that, and the strategy audit showed it
    passed with the entire fix disabled.
    """
    result = run_duel(Blind(), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS)

    assert len(set(result.path[:12])) >= 6, (
        "the blind policy used to visit four cells in eleven steps; "
        f"this replay visited only {len(set(result.path[:12]))}"
    )


def test_the_blind_thief_never_parks_on_one_cell(params: GameParams) -> None:
    """No absorbing fixed point — the specific shape the old bug settled into.

    It walked (3,3) to (6,5) in five steps and then played STAY for the other
    thirty, because at (6,5) every move scored below standing still. A policy
    with a fixed point loses to any opponent patient enough to arrive.
    """
    result = run_duel(Blind(), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS)

    longest = held = 1
    for earlier, later in zip(result.path, result.path[1:], strict=False):
        held = held + 1 if earlier == later else 1
        longest = max(longest, held)

    assert longest <= 4, f"the thief held one cell for {longest} consecutive turns"


def test_the_blind_thief_plays_a_different_line_each_sub_game(params: GameParams) -> None:
    """Silence is not an excuse to be predictable.

    A scripted opponent solved our previous thief by replaying one line at it
    three times, and within a single series a peer watches five sub-games before
    the sixth. `VARIATION_BAND` buys that variation out of moves that are within
    a point of the best rather than out of safety.
    """

    class Varying(Blind):
        def __init__(self, sub_game: int) -> None:
            super().__init__()
            self._sub_game = sub_game

        def pick_move(self, facts):
            facts.sub_game = self._sub_game
            return super().pick_move(facts)

    lines = {
        run_duel(Varying(sub), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS).path
        for sub in range(1, 7)
    }

    assert len(lines) >= 3, f"six sub-games produced only {len(lines)} distinct lines"


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


def test_the_six_sub_games_of_a_series_do_not_play_one_line(params: GameParams) -> None:
    """A scripted opponent solved our last thief by replaying one line at it.

    `hash()` on a tuple of two small ints is nearly linear, so consecutive
    sub-games mapped to the same residue: three distinct choices at step 1 and
    two at steps 2-3, out of four tied moves. The archive shows the cost — g04
    and g06 came out byte-identical. A digest spreads properly.
    """
    from najamjad_agent.constants import Move

    class Facts:
        def __init__(self, sub_game: int, step: int) -> None:
            self.sub_game, self.step = sub_game, step

    brain = ThiefBrain()
    tied = (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST)

    for step in range(1, 6):
        picks = {brain._break_tie(tied, Facts(sub, step)) for sub in range(1, 7)}  # noqa: SLF001
        assert len(picks) >= 3, f"step {step} varied over only {len(picks)} of 4 moves"


def test_tie_breaking_stays_reproducible_for_the_audit(params: GameParams) -> None:
    """Variation across games, never within a replay of one."""
    from najamjad_agent.constants import Move

    class Facts:
        def __init__(self, sub_game: int, step: int) -> None:
            self.sub_game, self.step = sub_game, step

    brain = ThiefBrain()
    tied = (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST)

    assert brain._break_tie(tied, Facts(3, 7)) == brain._break_tie(tied, Facts(3, 7))  # noqa: SLF001
