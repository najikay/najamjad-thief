"""The WebSocket frame contract.

Validation runs on every outbound frame, so these tests double as the guarantee
that a typo in a frame type is loud rather than a panel that quietly stops
updating — the failure mode A6's dashboard had.
"""

import pytest

from najamjad_agent.ui.frames import FRAME_TYPES, validate_frame


@pytest.mark.parametrize("kind", sorted(FRAME_TYPES))
def test_every_declared_frame_type_round_trips(kind):
    minimal = {
        "board": {"size": 7, "own_position": [0, 0]},
        "turn": {"phase": "committing", "locked": True},
    }
    frame = validate_frame({"type": kind, **minimal.get(kind, {})})

    assert frame["type"] == kind


def test_an_unknown_frame_type_is_rejected():
    with pytest.raises(ValueError, match="unknown frame type"):
        validate_frame({"type": "hetmap", "cells": []})


def test_a_frame_with_no_type_is_rejected():
    with pytest.raises(ValueError, match="unknown frame type"):
        validate_frame({"board": {}})


def test_extra_fields_survive_so_events_keep_their_payload():
    frame = validate_frame({"type": "event", "event": "llm.fallback", "provider": "deepseek"})

    assert frame["provider"] == "deepseek"


def test_a_frame_carrying_the_opponents_position_is_refused():
    with pytest.raises(ValueError, match="rules 8-9"):
        validate_frame({"type": "board", "size": 7, "own_position": [0, 0],
                        "opponent_position": [3, 3]})


def test_a_nonce_nested_inside_a_frame_is_refused():
    with pytest.raises(ValueError, match="rules 8-9"):
        validate_frame({"type": "event", "event": "turn.committed", "record": {"nonce": "beef"}})


def test_a_board_frame_missing_required_fields_fails_validation():
    with pytest.raises(Exception, match="own_position"):
        validate_frame({"type": "board", "size": 7})


def test_a_report_frame_can_carry_an_undecided_agreement():
    frame = validate_frame({"type": "report", "reconciled": False, "agreement": None})

    assert frame["agreement"] is None
