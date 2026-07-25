"""Tests for online opponent learning — sized to the data we actually get.

Roughly 210 observations per series (35 steps x 6 mini-games): ample for a few
parameters, nowhere near enough for a learned policy. These tests pin that the
model adapts within a series and persists across a restart.
"""

from pathlib import Path

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.strategy.opponent_model import NEUTRAL_CREDIBILITY, OpponentModel


@pytest.fixture()
def model() -> OpponentModel:
    return OpponentModel(group_id="rival")


def test_a_new_opponent_starts_neutral(model: OpponentModel) -> None:
    """No prior evidence means no prejudice, in either direction."""
    assert model.credibility == NEUTRAL_CREDIBILITY
    assert model.hints_seen == 0


def test_confirmed_hints_raise_credibility(model: OpponentModel) -> None:
    for _ in range(5):
        model.record_hint("consistent")
    assert model.credibility > 0.8


def test_refuted_hints_lower_credibility(model: OpponentModel) -> None:
    for _ in range(5):
        model.record_hint("refuted")
    assert model.credibility < 0.2


def test_an_unverifiable_hint_changes_nothing(model: OpponentModel) -> None:
    """Otherwise an opponent rebuilds trust by saying nothing checkable."""
    before = model.credibility
    model.record_hint("unknown")
    assert model.credibility == before
    assert model.hints_seen == 0


def test_credibility_stays_bounded(model: OpponentModel) -> None:
    for _ in range(100):
        model.record_hint("consistent")
    assert model.credibility <= 1.0
    for _ in range(100):
        model.record_hint("refuted")
    assert model.credibility >= 0.0


def test_a_liar_who_reforms_is_tracked_not_condemned(model: OpponentModel) -> None:
    """Exponential weighting means recent evidence dominates."""
    for _ in range(5):
        model.record_hint("refuted")
    caught = model.credibility
    for _ in range(10):
        model.record_hint("consistent")
    assert model.credibility > caught + 0.4


def test_the_refute_rate_summarises_their_honesty(model: OpponentModel) -> None:
    model.record_hint("consistent")
    model.record_hint("refuted")
    model.record_hint("refuted")
    assert model.refute_rate == pytest.approx(2 / 3)


def test_the_refute_rate_of_an_unobserved_opponent_is_zero(model: OpponentModel) -> None:
    assert model.refute_rate == 0.0


def test_movement_tendencies_are_learned(model: OpponentModel) -> None:
    for move in (Move.NORTH, Move.NORTH, Move.NORTH, Move.EAST):
        model.record_move(move)
    prior = model.movement_prior()
    assert prior["N"] == pytest.approx(0.75)
    assert prior["E"] == pytest.approx(0.25)


def test_a_movement_prior_without_data_is_empty(model: OpponentModel) -> None:
    assert model.movement_prior() == {}


def test_a_staller_is_identified(model: OpponentModel) -> None:
    """A thief playing the survival clock changes how we spend barriers."""
    for _ in range(4):
        model.record_move(Move.STAY)
    model.record_move(Move.NORTH)
    assert model.favours_staying()


def test_a_mobile_opponent_is_not_flagged_as_a_staller(model: OpponentModel) -> None:
    for move in (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST):
        model.record_move(move)
    assert not model.favours_staying()


def test_directness_rises_when_they_close_decisively(model: OpponentModel) -> None:
    for _ in range(6):
        model.record_move(Move.NORTH, closed_distance=True)
    assert model.directness > 0.7


def test_directness_falls_when_they_wander(model: OpponentModel) -> None:
    for _ in range(6):
        model.record_move(Move.NORTH, closed_distance=False)
    assert model.directness < 0.3


def test_a_wire_move_string_is_accepted(model: OpponentModel) -> None:
    """Opponent payloads arrive as strings, not our enum."""
    model.record_move("N")
    assert model.movement_prior()["N"] == 1.0


def test_the_model_persists_across_a_restart(tmp_path: Path) -> None:
    """A series spans six mini-games; losing what we learned wastes them."""
    model = OpponentModel(group_id="rival")
    for _ in range(4):
        model.record_hint("refuted")
    model.record_move(Move.NORTH, closed_distance=True)
    model.save(tmp_path)

    reloaded = OpponentModel.load(tmp_path, "rival")
    assert reloaded.group_id == "rival"
    assert reloaded.credibility == pytest.approx(model.credibility, abs=1e-3)
    assert reloaded.hints_refuted == 4
    assert reloaded.move_counts == {"N": 1}


def test_an_unknown_opponent_loads_as_neutral(tmp_path: Path) -> None:
    fresh = OpponentModel.load(tmp_path, "never-met")
    assert fresh.credibility == NEUTRAL_CREDIBILITY
    assert fresh.group_id == "never-met"


def test_unknown_fields_in_a_saved_model_are_ignored(tmp_path: Path) -> None:
    """A model written by a newer version must not crash an older one."""
    (tmp_path / "opponent_model.json").write_text(
        '{"group_id": "rival", "credibility": 0.7, "future_field": 1}', encoding="utf-8"
    )
    assert OpponentModel.load(tmp_path, "rival").credibility == 0.7


def test_the_saved_form_is_readable_for_the_report(tmp_path: Path) -> None:
    model = OpponentModel(group_id="rival")
    model.record_hint("refuted")
    payload = model.as_dict()
    assert set(payload) >= {"group_id", "credibility", "hints_seen", "move_counts"}
    assert model.save(tmp_path).name == "opponent_model.json"
