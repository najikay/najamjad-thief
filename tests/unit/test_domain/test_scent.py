"""Tests for scent field state, wire format, clamping, and untrusted ingress."""

import pytest

from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.scent_models import ScentModel


@pytest.fixture()
def field() -> ScentField:
    return ScentField(board_size=7)


def test_deposit_marks_the_centre_at_full_strength(field: ScentField) -> None:
    field.deposit((3, 3))
    assert field.intensity_at((3, 3)) == 0.9


def test_unscented_cells_read_zero(field: ScentField) -> None:
    assert field.intensity_at((0, 0)) == 0.0


def test_deposit_max_merges_rather_than_accumulating(field: ScentField) -> None:
    """Repeated presence must never push a cell above the agreed ceiling."""
    for _ in range(5):
        field.deposit((3, 3))
    assert field.intensity_at((3, 3)) == 0.9


def test_overlapping_deposits_keep_the_strongest_value(field: ScentField) -> None:
    field.deposit((3, 3))
    field.deposit((3, 4))
    assert field.intensity_at((3, 4)) == 0.9
    assert field.intensity_at((3, 3)) == 0.9


def test_deposit_rejects_out_of_range_intensity(field: ScentField) -> None:
    with pytest.raises(ValueError, match="must lie in"):
        field.deposit((3, 3), intensity=1.5)
    with pytest.raises(ValueError, match="must lie in"):
        field.deposit((3, 3), intensity=0.0)


def test_decay_reduces_all_known_intensities(field: ScentField) -> None:
    field.deposit((3, 3))
    field.decay_all()
    assert field.intensity_at((3, 3)) == pytest.approx(0.81)


def test_repeated_decay_drops_the_trail_and_frees_memory(field: ScentField) -> None:
    field.deposit((3, 3))
    for _ in range(200):
        field.decay_all()
    assert field.intensity_at((3, 3)) == 0.0
    assert field.snapshot() == {}


def test_values_never_exceed_the_ceiling_or_go_negative(field: ScentField) -> None:
    field.deposit((3, 3))
    field.absorb({"3,3": 5.0, "0,0": 0.4})
    field.decay_all()
    assert all(0.0 <= value <= field.ceiling for value in field.snapshot().values())


def test_snapshot_uses_the_reference_wire_format(field: ScentField) -> None:
    field.deposit((3, 3))
    snapshot = field.snapshot()
    assert snapshot["3,3"] == 0.9
    assert all(isinstance(key, str) and "," in key for key in snapshot)


def test_snapshot_omits_zero_cells_and_never_leaks_a_position(field: ScentField) -> None:
    field.deposit((3, 3))
    snapshot = field.snapshot()
    assert all(value > 0.0 for value in snapshot.values())
    assert "position" not in snapshot and "3" not in snapshot.values()


def test_absorb_merges_an_opponent_field(field: ScentField) -> None:
    assert field.absorb({"2,2": 0.62, "2,3": 0.9}) == []
    assert field.intensity_at((2, 2)) == 0.62
    assert field.intensity_at((2, 3)) == 0.9


def test_absorb_keeps_the_stronger_of_the_two_fields(field: ScentField) -> None:
    field.absorb({"2,2": 0.62})
    field.absorb({"2,2": 0.2})
    assert field.intensity_at((2, 2)) == 0.62


def test_absorb_reports_out_of_bounds_cells_without_crashing(field: ScentField) -> None:
    problems = field.absorb({"99,0": 0.5, "-1,2": 0.5, "3,3": 0.5})
    assert len(problems) == 2
    assert field.intensity_at((3, 3)) == 0.5


def test_absorb_reports_malformed_keys(field: ScentField) -> None:
    problems = field.absorb({"not-a-cell": 0.5, "1,2,3": 0.4, "a,b": 0.3})
    assert len(problems) == 3
    assert field.snapshot() == {}


def test_absorb_clamps_and_rejects_bad_intensities(field: ScentField) -> None:
    problems = field.absorb({"1,1": 9.9, "1,2": "high", "1,3": -0.5, "1,4": float("nan")})
    assert field.intensity_at((1, 1)) == 0.9, "over-range intensity clamped to the ceiling"
    assert len(problems) == 3


def test_strongest_cell_finds_the_peak(field: ScentField) -> None:
    field.absorb({"1,1": 0.2, "5,5": 0.62, "2,2": 0.42})
    assert field.strongest_cell() == (5, 5)


def test_strongest_cell_is_none_on_an_empty_field(field: ScentField) -> None:
    assert field.strongest_cell() is None


def test_reference_model_field_decays_absolutely() -> None:
    other = ScentField(board_size=7, model=ScentModel.REFERENCE)
    other.deposit((3, 3))
    other.decay_all()
    assert other.intensity_at((3, 3)) == pytest.approx(0.8)
    assert other.model is ScentModel.REFERENCE


def test_our_emission_matches_the_published_interop_field() -> None:
    """The physics both peers must share, checked against an outside source.

    Nothing crashes when two teams run different scent models: the grid is not
    part of the commit, so every audit still passes. Both sides simply infer the
    wrong position from each other's field for the whole series, and each
    concludes the other is buggy.

    `ScentField` defaults to `BOOK` and nothing overrode it, so we emitted the
    radial relative-falloff field while the league's CORE model is subtractive
    Chebyshev. These are the exact centre and corner fields from the interop
    kit's `vectors/pheromone.json`; our `REFERENCE` model reproduces both and
    `BOOK` reproduces neither.
    """
    from najamjad_agent.domain.scent_models import ScentModel, emission_field

    centre = {
        (1, 1): 0.3, (1, 2): 0.3, (1, 3): 0.3, (1, 4): 0.3, (1, 5): 0.3,
        (2, 1): 0.3, (2, 2): 0.6, (2, 3): 0.6, (2, 4): 0.6, (2, 5): 0.3,
        (3, 1): 0.3, (3, 2): 0.6, (3, 3): 0.9, (3, 4): 0.6, (3, 5): 0.3,
        (4, 1): 0.3, (4, 2): 0.6, (4, 3): 0.6, (4, 4): 0.6, (4, 5): 0.3,
        (5, 1): 0.3, (5, 2): 0.3, (5, 3): 0.3, (5, 4): 0.3, (5, 5): 0.3,
    }
    corner = {
        (0, 0): 0.9, (0, 1): 0.6, (0, 2): 0.3,
        (1, 0): 0.6, (1, 1): 0.6, (1, 2): 0.3,
        (2, 0): 0.3, (2, 1): 0.3, (2, 2): 0.3,
    }

    emitted = {c: round(v, 3) for c, v in emission_field((3, 3), 0.9, 5, ScentModel.REFERENCE, 7).items()}
    clipped = {c: round(v, 3) for c, v in emission_field((0, 0), 0.9, 5, ScentModel.REFERENCE, 7).items()}

    assert emitted == centre
    assert clipped == corner


def test_the_league_model_is_what_production_builds() -> None:
    """The seam. Matching physics in a helper nobody calls is worth nothing."""

    from najamjad_agent.constants import Role
    from najamjad_agent.domain.params import GameParams
    from najamjad_agent.domain.scent_models import ScentModel
    from najamjad_agent.sdk.state_setup import state_factory
    from tests.role_config import load_role_config

    manager = load_role_config()
    params = GameParams.from_config({
        "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
        "movement_and_barriers": {
            "move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
            "max_moves": 35, "survival_threshold": 35,
        },
    })
    state = state_factory(manager)(params, Role.THIEF, 1)

    assert state.own_scent.model is ScentModel.REFERENCE
