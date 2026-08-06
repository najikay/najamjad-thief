"""Tests for reading position out of the declarations the rules make mandatory."""

import pytest

from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.cop_sighting import (
    BARRIER_CONFIDENCE,
    CLAIM_CONFIDENCE,
    IMPLAUSIBLE_CONFIDENCE,
    from_barrier,
    from_claim,
    plausible,
)
from najamjad_agent.domain.params import GameParams

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
def board() -> Board:
    return Board(GameParams.from_config(CONFIG))


def test_a_claim_is_a_single_exact_cell() -> None:
    """`evaluate_capture` requires the cop to occupy the cell it claims."""
    sighting = from_claim((4, 2), step=7)

    assert sighting.exact
    assert sighting.cells == ((4, 2),)
    assert sighting.confidence == CLAIM_CONFIDENCE


def test_a_barrier_names_the_reach_set_the_barrier_law_allows(board: Board) -> None:
    """Own cell or one orthogonal step, in lieu of moving (FR-ENG-3)."""
    sighting = from_barrier(board.with_barrier((3, 3)), (3, 3), step=2)

    assert sighting is not None
    assert set(sighting.cells) == {(2, 3), (4, 3), (3, 2), (3, 4)}
    assert sighting.confidence == BARRIER_CONFIDENCE


def test_a_barrier_in_a_corner_names_only_the_cells_that_exist(board: Board) -> None:
    sighting = from_barrier(board.with_barrier((0, 0)), (0, 0), step=1)

    assert sighting is not None
    assert set(sighting.cells) == {(1, 0), (0, 1)}


def test_a_barrier_with_no_open_neighbours_names_nothing(board: Board) -> None:
    """A sealed pocket yields no candidates, and must not yield an empty claim."""
    walled = board.with_barrier((0, 1)).with_barrier((1, 0)).with_barrier((0, 0))

    assert from_barrier(walled, (0, 0), step=5) is None


def test_a_barrier_is_never_reported_as_certainty(board: Board) -> None:
    """Five candidates is knowledge; one confident cell would be a fabrication."""
    sighting = from_barrier(board.with_barrier((4, 4)), (4, 4), step=3)

    assert sighting is not None
    assert not sighting.exact
    assert sighting.confidence < CLAIM_CONFIDENCE


def test_a_sighting_with_no_predecessor_is_accepted_as_is() -> None:
    sighting = from_claim((0, 0), step=1)

    assert plausible(sighting, None) is sighting


def test_a_reachable_sighting_keeps_its_confidence() -> None:
    """One cell per turn is legal movement, so it is ordinary evidence."""
    first = from_claim((3, 3), step=4)
    second = from_claim((3, 4), step=5)

    assert plausible(second, first).confidence == CLAIM_CONFIDENCE


def test_a_sighting_that_teleports_is_downgraded_not_refused() -> None:
    """A bluff must cost the opponent our confidence, not our whole belief.

    Refusing outright would let a peer freeze our belief by declaring nonsense,
    which is a cheaper attack than the one being defended against.
    """
    first = from_claim((0, 0), step=1)
    far = from_claim((6, 6), step=2)

    checked = plausible(far, first)

    assert checked.confidence == IMPLAUSIBLE_CONFIDENCE
    assert checked.cells == far.cells
    assert "implausible" in checked.source


def test_a_late_sighting_is_judged_against_the_time_that_passed() -> None:
    """Five turns of silence permits five cells of travel; that is not a bluff."""
    first = from_claim((0, 0), step=1)
    later = from_claim((0, 5), step=6)

    assert plausible(later, first, elapsed=5).confidence == CLAIM_CONFIDENCE


def test_a_barrier_predecessor_is_given_the_slack_its_ambiguity_earns(
    board: Board,
) -> None:
    """A five-cell set is already uncertain by one step; do not punish it twice."""
    barrier = from_barrier(board.with_barrier((3, 3)), (3, 3), step=2)
    assert barrier is not None
    following = from_claim((2, 1), step=3)

    assert plausible(following, barrier).confidence == CLAIM_CONFIDENCE


def test_the_event_form_carries_what_a_replay_needs() -> None:
    recorded = from_claim((2, 5), step=9).as_event()

    assert recorded["cells"] == [[2, 5]]
    assert recorded["step"] == 9
    assert recorded["source"] == "capture_claim"


def test_observing_a_claim_moves_the_belief_peak_onto_it(board: Board) -> None:
    """The end-to-end effect the whole change exists for."""
    belief = BeliefGrid(board)
    belief.observe_reach(((5, 1),), CLAIM_CONFIDENCE)

    assert belief.peak() == (5, 1)
    assert belief.probability_at((5, 1)) > 0.9


def test_observing_a_reach_set_spreads_mass_across_it(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.observe_reach(((2, 3), (4, 3), (3, 2), (3, 4)), BARRIER_CONFIDENCE)

    inside = sum(belief.probability_at(cell) for cell in ((2, 3), (4, 3), (3, 2), (3, 4)))
    assert inside > 0.5
    assert belief.probability_at((0, 0)) < belief.probability_at((2, 3))


def test_a_declaration_naming_nothing_we_track_is_ignored(board: Board) -> None:
    """Zeroing the grid would trip collapse-recovery and reset us to uniform.

    That is strictly worse than the belief we already hold, and an opponent
    could trigger it at will by naming a cell we believe is walled.
    """
    belief = BeliefGrid(board)
    belief.observe_reach(((5, 1),), CLAIM_CONFIDENCE)
    before = belief.as_dict()

    belief.observe_reach(((99, 99),), CLAIM_CONFIDENCE)

    assert belief.as_dict() == before


def test_a_mistaken_observation_stays_recoverable(board: Board) -> None:
    """No evidence may drive a cell to a hard zero; a zero never recovers."""
    belief = BeliefGrid(board)
    belief.observe_reach(((5, 1),), CLAIM_CONFIDENCE)

    assert belief.probability_at((0, 0)) > 0.0
