"""Tests for scent emission/decay models, incl. the book's binding numeric example."""

import pytest

from najamjad_agent.domain.scent_models import (
    BOOK_FIELD_5X5,
    ScentModel,
    decay_value,
    emission_field,
    model_fingerprint,
)

CENTER = (3, 3)


def _field_rows(field: dict, center: tuple[int, int], half: int) -> list[list[float]]:
    rows = []
    for row in range(center[0] - half, center[0] + half + 1):
        rows.append([field.get((row, col), 0.0) for col in range(center[1] - half, center[1] + half + 1)])
    return rows


def test_book_numeric_example_matches_exactly() -> None:
    """The 5x5 field is the value both teams sign (book PAGE 44, rule 23)."""
    field = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.BOOK, board_size=7)
    assert _field_rows(field, CENTER, 2) == BOOK_FIELD_5X5


def test_book_field_constant_is_the_published_table() -> None:
    assert BOOK_FIELD_5X5 == [
        [0.04, 0.14, 0.20, 0.14, 0.04],
        [0.14, 0.42, 0.62, 0.42, 0.14],
        [0.20, 0.62, 0.90, 0.62, 0.20],
        [0.14, 0.42, 0.62, 0.42, 0.14],
        [0.04, 0.14, 0.20, 0.14, 0.04],
    ]


def test_centre_intensity_is_exact(board_size: int = 7) -> None:
    field = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.BOOK, board_size=board_size)
    assert field[CENTER] == 0.9


def test_falloff_is_monotone_in_distance() -> None:
    field = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.BOOK, board_size=7)
    assert field[(3, 4)] > field[(2, 4)] > field[(3, 5)] > field[(2, 5)] > field[(1, 5)]


def test_emission_is_clipped_to_the_board() -> None:
    field = emission_field((0, 0), 0.9, grid_size=5, model=ScentModel.BOOK, board_size=7)
    assert all(0 <= row < 7 and 0 <= col < 7 for row, col in field)
    assert field[(0, 0)] == 0.9


def test_reference_model_uses_chebyshev_linear_falloff() -> None:
    """The lecturer's simulator differs from the book; we can match it on request."""
    field = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.REFERENCE, board_size=7)
    assert field[CENTER] == 0.9
    assert field[(3, 4)] == pytest.approx(0.6)
    assert field[(2, 4)] == pytest.approx(0.6), "diagonal equals orthogonal under Chebyshev"
    assert field[(3, 5)] == pytest.approx(0.3)


def test_book_and_reference_models_disagree() -> None:
    """Guards the reason the model is negotiated and hashed before play."""
    book = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.BOOK, board_size=7)
    reference = emission_field(CENTER, 0.9, grid_size=5, model=ScentModel.REFERENCE, board_size=7)
    assert book != reference


def test_book_decay_is_relative() -> None:
    """Book: tau(t+1) = max(0, (1-rho)*tau); rho = 0.10 per full turn."""
    assert decay_value(0.9, 0.10, ScentModel.BOOK) == pytest.approx(0.81)
    assert decay_value(0.81, 0.10, ScentModel.BOOK) == pytest.approx(0.729)


def test_reference_decay_is_absolute() -> None:
    assert decay_value(0.9, 0.10, ScentModel.REFERENCE) == pytest.approx(0.8)


def test_decay_never_goes_negative() -> None:
    assert decay_value(0.05, 0.10, ScentModel.REFERENCE) == 0.0
    assert decay_value(0.0, 0.10, ScentModel.BOOK) == 0.0


def test_relative_decay_reaches_zero_instead_of_a_fixed_point() -> None:
    """Rounding alone leaves 0.005 self-sustaining; the epsilon floor kills it."""
    value = 0.9
    for _ in range(500):
        value = decay_value(value, 0.10, ScentModel.BOOK)
    assert value == 0.0


def test_epsilon_floor_does_not_prune_faint_published_values() -> None:
    """The book's weakest published intensity (0.04) must survive a decay step."""
    assert decay_value(0.04, 0.10, ScentModel.BOOK) > 0.0


def test_book_deposit_stays_readable_for_about_six_turns() -> None:
    """Book PAGE 45: a single deposit is readable ~6-7 turns (half-peak near 7)."""
    value = 0.9
    for _ in range(7):
        value = decay_value(value, 0.10, ScentModel.BOOK)
    assert 0.4 < value < 0.5


def test_model_fingerprint_is_stable_and_model_specific() -> None:
    """The fingerprint is what gets SHA-256 locked with the opponent (rule 23)."""
    first = model_fingerprint(ScentModel.BOOK, center=0.9, decay=0.10, grid_size=5)
    again = model_fingerprint(ScentModel.BOOK, center=0.9, decay=0.10, grid_size=5)
    other = model_fingerprint(ScentModel.REFERENCE, center=0.9, decay=0.10, grid_size=5)
    assert first == again
    assert first != other
    assert len(first) == 64
