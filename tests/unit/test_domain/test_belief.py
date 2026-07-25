"""Tests for the Bayesian belief grid: prior, diffusion, fusion, exclusion."""

import pytest

from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board

EPS = 1e-9


def test_prior_is_uniform_over_open_cells(board: Board) -> None:
    belief = BeliefGrid(board)
    assert belief.total() == pytest.approx(1.0)
    assert belief.probability_at((0, 0)) == pytest.approx(1 / 49)


def test_barriers_are_excluded_from_the_prior(board: Board) -> None:
    belief = BeliefGrid(board.with_barrier((2, 2)))
    assert belief.probability_at((2, 2)) == 0.0
    assert belief.total() == pytest.approx(1.0)
    assert belief.probability_at((0, 0)) == pytest.approx(1 / 48)


def test_known_empty_cells_are_excluded_from_the_prior(board: Board) -> None:
    belief = BeliefGrid(board, known_empty=((0, 0),))
    assert belief.probability_at((0, 0)) == 0.0
    assert belief.total() == pytest.approx(1.0)


def test_diffusion_preserves_total_probability(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.diffuse()
    assert belief.total() == pytest.approx(1.0)


def test_diffusion_spreads_a_point_mass_to_neighbours(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.apply_likelihood({(3, 3): 1.0})
    belief.exclude(tuple(cell for cell in board.cells() if cell != (3, 3)))
    belief.diffuse(stay_weight=0.2)
    assert belief.probability_at((3, 3)) == pytest.approx(0.2, abs=1e-6)
    for neighbour in [(2, 3), (4, 3), (3, 2), (3, 4)]:
        assert belief.probability_at(neighbour) == pytest.approx(0.2, abs=1e-6)


def test_diffusion_does_not_leak_mass_through_barriers(board: Board) -> None:
    walled = board.with_barrier((3, 4))
    belief = BeliefGrid(walled)
    belief.exclude(tuple(cell for cell in walled.cells() if cell != (3, 3)))
    belief.diffuse()
    assert belief.probability_at((3, 4)) == 0.0
    assert belief.total() == pytest.approx(1.0)


def test_diffusion_does_not_leak_mass_off_board(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.exclude(tuple(cell for cell in board.cells() if cell != (0, 0)))
    belief.diffuse()
    assert belief.total() == pytest.approx(1.0)
    assert all(board.is_open(cell) for cell in belief.as_dict())


def test_scent_update_favours_the_strongest_cell(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.update_scent({(5, 5): 0.9, (5, 4): 0.42})
    assert belief.peak() == (5, 5)
    assert belief.probability_at((5, 5)) > belief.probability_at((5, 4))
    assert belief.probability_at((5, 4)) > belief.probability_at((0, 0))


def test_scent_update_keeps_a_valid_distribution(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.update_scent({(1, 1): 0.62})
    assert belief.total() == pytest.approx(1.0)
    assert all(value >= 0.0 for value in belief.as_dict().values())


def test_empty_scent_field_leaves_belief_usable(board: Board) -> None:
    """No observation must not collapse the distribution (graceful degradation)."""
    belief = BeliefGrid(board)
    belief.update_scent({})
    assert belief.total() == pytest.approx(1.0)


def test_partial_trust_softens_the_scent_update(board: Board) -> None:
    confident = BeliefGrid(board)
    cautious = BeliefGrid(board)
    confident.update_scent({(5, 5): 0.9}, trust=1.0)
    cautious.update_scent({(5, 5): 0.9}, trust=0.5)
    assert confident.probability_at((5, 5)) > cautious.probability_at((5, 5))
    assert cautious.probability_at((0, 0)) > confident.probability_at((0, 0))


def test_exclusion_zeroes_a_cell_and_renormalises(board: Board) -> None:
    belief = BeliefGrid(board)
    belief.exclude(((0, 0), (0, 1)))
    assert belief.probability_at((0, 0)) == 0.0
    assert belief.total() == pytest.approx(1.0)


def test_total_collapse_recovers_to_a_uniform_prior(board: Board) -> None:
    """Contradictory evidence must not leave an unusable NaN distribution."""
    belief = BeliefGrid(board)
    belief.apply_likelihood(dict.fromkeys(board.cells(), 0.0))
    assert belief.total() == pytest.approx(1.0)
    assert belief.probability_at((3, 3)) == pytest.approx(1 / 49)


def test_no_cell_is_permanently_impossible_after_a_zero_likelihood(board: Board) -> None:
    """A cell zeroed by one observation can be revived by later evidence."""
    belief = BeliefGrid(board)
    belief.apply_likelihood({(3, 3): 0.0})
    assert belief.probability_at((3, 3)) > 0.0
    belief.apply_likelihood({(3, 3): 10.0})
    assert belief.probability_at((3, 3)) > 0.0


def test_peak_is_deterministic_under_ties(board: Board) -> None:
    belief = BeliefGrid(board)
    assert belief.peak() == (0, 0)


def test_peak_is_none_when_no_cells_remain(board: Board) -> None:
    blocked = Board(board.params, barriers=set(board.cells()))
    assert BeliefGrid(blocked).peak() is None


def test_belief_exposes_the_board_it_tracks(board: Board) -> None:
    assert BeliefGrid(board).board is board


def test_diffusion_keeps_mass_on_a_fully_enclosed_cell(board: Board) -> None:
    """An opponent walled in on all four sides can only have stayed put."""
    walled = board
    for cell in [(2, 3), (4, 3), (3, 2), (3, 4)]:
        walled = walled.with_barrier(cell)
    belief = BeliefGrid(walled)
    belief.exclude(tuple(cell for cell in walled.cells() if cell != (3, 3)))
    belief.diffuse()
    assert belief.probability_at((3, 3)) == pytest.approx(1.0)


def test_scent_update_on_a_fully_blocked_board_is_survivable(board: Board) -> None:
    """Degenerate board (no open cells): must not raise or produce NaN."""
    blocked = Board(board.params, barriers=set(board.cells()))
    belief = BeliefGrid(blocked)
    belief.update_scent({(3, 3): 0.9})
    assert belief.as_dict() == {}
    assert belief.peak() is None
