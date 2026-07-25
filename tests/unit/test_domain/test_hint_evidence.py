"""Tests for hint likelihood, credibility tracking, and scent-based lie detection."""

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.hint_evidence import (
    CredibilityTracker,
    HintClaim,
    claim_likelihood,
    scent_consistency,
)

CELLS = tuple((row, col) for row in range(7) for col in range(7))
REFERENCE = (3, 3)


def test_directional_claim_boosts_cells_in_that_direction() -> None:
    claim = HintClaim(direction=Move.NORTH, text="heading north past the park")
    likelihood = claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0)
    assert likelihood[(1, 3)] > 1.0, "north of the reference is supported"
    assert likelihood[(5, 3)] < 1.0, "south of the reference is contradicted"


def test_landmark_claim_boosts_the_named_cells() -> None:
    claim = HintClaim(landmark_cells=((6, 6), (6, 5)), text="slipping past Times Square")
    likelihood = claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0)
    assert likelihood[(6, 6)] > 1.0
    assert likelihood[(0, 0)] < 1.0


def test_uninformative_hint_is_an_identity_update() -> None:
    """Parse failure or empty hint must never move belief (FR-LLM-5)."""
    likelihood = claim_likelihood(CELLS, HintClaim(text="???"), REFERENCE, credibility=1.0)
    assert set(likelihood.values()) == {1.0}


def test_zero_credibility_is_an_identity_update() -> None:
    claim = HintClaim(direction=Move.NORTH)
    assert set(claim_likelihood(CELLS, claim, REFERENCE, credibility=0.0).values()) == {1.0}


def test_credibility_scales_the_evidence_strength() -> None:
    claim = HintClaim(direction=Move.NORTH)
    weak = claim_likelihood(CELLS, claim, REFERENCE, credibility=0.25)
    strong = claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0)
    assert strong[(1, 3)] > weak[(1, 3)] > 1.0


def test_likelihood_never_reaches_zero() -> None:
    """A lie must not make a cell impossible — only less likely."""
    claim = HintClaim(direction=Move.NORTH)
    likelihood = claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0)
    assert min(likelihood.values()) > 0.0


def test_credibility_starts_neutral_and_is_bounded() -> None:
    tracker = CredibilityTracker()
    assert tracker.coefficient == pytest.approx(0.5)
    for _ in range(50):
        tracker.record(consistent=True)
    assert tracker.coefficient <= 1.0
    for _ in range(50):
        tracker.record(consistent=False)
    assert tracker.coefficient >= 0.0


def test_confirmed_claim_raises_credibility() -> None:
    tracker = CredibilityTracker()
    assert tracker.record(consistent=True) > 0.5


def test_refuted_claim_lowers_credibility() -> None:
    tracker = CredibilityTracker()
    assert tracker.record(consistent=False) < 0.5


def test_credibility_prior_can_be_carried_between_mini_games() -> None:
    assert CredibilityTracker(coefficient=0.1).coefficient == pytest.approx(0.1)


def test_book_worked_example_detects_the_lie() -> None:
    """Book PAGE 46: 'moved north' with empty north and a fresh south-east trail."""
    claim = HintClaim(direction=Move.NORTH, text="I slipped north")
    intensities = {(2, 3): 0.0, (1, 3): 0.0, (5, 5): 0.81, (5, 4): 0.62}
    assert scent_consistency(claim, intensities, REFERENCE) == "refuted"


def test_supporting_scent_confirms_the_claim() -> None:
    claim = HintClaim(direction=Move.NORTH)
    intensities = {(1, 3): 0.81, (2, 3): 0.62}
    assert scent_consistency(claim, intensities, REFERENCE) == "consistent"


def test_empty_scent_field_yields_no_verdict() -> None:
    assert scent_consistency(HintClaim(direction=Move.NORTH), {}, REFERENCE) == "unknown"


def test_noise_level_scent_yields_no_verdict() -> None:
    intensities = {(1, 3): 0.01, (5, 5): 0.02}
    assert scent_consistency(HintClaim(direction=Move.NORTH), intensities, REFERENCE) == "unknown"


def test_stay_claim_carries_no_directional_information() -> None:
    """'I held position' supports no cell over another (zero displacement)."""
    claim = HintClaim(direction=Move.STAY, text="holding still")
    likelihood = claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0)
    weights = list(likelihood.values())
    assert all(weight == pytest.approx(weights[0]) for weight in weights), "uniform => no effect"
    assert scent_consistency(claim, {(1, 3): 0.9}, REFERENCE) == "unknown"


def test_landmark_only_claim_cannot_be_scent_checked() -> None:
    claim = HintClaim(landmark_cells=((0, 0),))
    assert scent_consistency(claim, {(5, 5): 0.9}, REFERENCE) == "unknown"


def test_hint_cannot_override_contradicting_scent(board: Board) -> None:
    """Fusion order (FR-STR-1): testimony re-weights, physics decides."""
    belief = BeliefGrid(board)
    belief.update_scent({(5, 5): 0.9, (5, 4): 0.62}, trust=1.0)
    liar = HintClaim(direction=Move.NORTH, text="far to the north")
    belief.apply_likelihood(claim_likelihood(CELLS, liar, REFERENCE, credibility=1.0))
    assert belief.peak() == (5, 5), "scent mass still wins over a confident lie"
    assert belief.total() == pytest.approx(1.0)


def test_credible_hint_breaks_a_scent_tie(board: Board) -> None:
    """With no scent evidence, testimony is allowed to be decisive."""
    belief = BeliefGrid(board)
    claim = HintClaim(direction=Move.NORTH)
    belief.apply_likelihood(claim_likelihood(CELLS, claim, REFERENCE, credibility=1.0))
    assert belief.peak()[0] < REFERENCE[0]
