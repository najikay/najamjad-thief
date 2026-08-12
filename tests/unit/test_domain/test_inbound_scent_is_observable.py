"""What the opponent's grid contained, not merely what was wrong with it.

Absorbing silently made a peer sending 29 cells and a peer sending none look
identical in our own logs. "Does this opponent emit scent at all?" has therefore
been unanswerable against two of them, and the sealed records cannot settle it
either: the league's default `smell_binding: none` adds no grid key to a record
by design, so an empty audit trail is evidence of nothing.

It is also the measurement that decides a real question. A peer that transmits
its field post-decay should not have it decayed again on receipt, or its trail
ages twice in our belief and we read it fainter than it is. Whether that applies
depends on what actually arrives, which until now we did not record.
"""

from __future__ import annotations

from typing import Any

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.game_state import GameState
from tests.fakes.orchestration import build_state


@pytest.fixture()
def state() -> GameState:
    """A cop's state, so the opponent whose grid we absorb is the thief."""
    return build_state(Role.COP)


def _events(state: Any, message: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one absorb and return the events it emitted."""
    from najamjad_agent.domain.turn_ingress import absorb_turn

    seen: list[dict[str, Any]] = []

    def event(name: str, **fields: Any) -> None:
        seen.append({"event": name, **fields})

    absorb_turn(state, message, event)
    return seen


def _absorbed(seen: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((e for e in seen if e["event"] == "scent.absorbed"), None)


def test_a_full_grid_is_recorded_with_its_size_and_peak(state) -> None:
    """The ordinary case: a talking peer is visibly a talking peer."""
    grid = {"3,3": 0.9, "3,4": 0.6, "2,3": 0.6, "1,1": 0.3}

    absorbed = _absorbed(_events(state, {
        "step": 1, "sender": "thief", "commit": "a" * 64, "smell_grid": grid,
    }))

    assert absorbed is not None, "an arriving grid must be recorded"
    assert absorbed["cells"] == 4
    assert absorbed["peak"] == 0.9
    assert absorbed["rejected"] == 0


def test_a_silent_peer_is_recorded_as_silent_rather_than_not_recorded(state) -> None:
    """The case that was invisible, and the whole reason this exists.

    An empty grid must produce an event saying zero cells — not no event at all,
    which is what a missing key and a working peer both used to look like.
    """
    absorbed = _absorbed(_events(state, {
        "step": 1, "sender": "thief", "commit": "b" * 64, "smell_grid": {},
    }))

    assert absorbed is not None, "silence must be recorded, not inferred later"
    assert absorbed["cells"] == 0
    assert absorbed["peak"] == 0.0


def test_a_missing_key_reads_the_same_as_an_empty_one(state) -> None:
    """A peer omitting the field is silent, and must be logged as silent."""
    absorbed = _absorbed(_events(state, {
        "step": 1, "sender": "thief", "commit": "c" * 64,
    }))

    assert absorbed is not None
    assert absorbed["cells"] == 0


def test_rejected_cells_are_counted_alongside_what_was_kept(state) -> None:
    """A partly-malformed grid is data about the peer, not just an error."""
    seen = _events(state, {
        "step": 1, "sender": "thief", "commit": "d" * 64,
        "smell_grid": {"3,3": 0.9, "not-a-cell": 0.5},
    })
    absorbed = _absorbed(seen)

    assert absorbed is not None
    assert absorbed["cells"] == 2, "cells counts what arrived, before validation"
    assert absorbed["rejected"] >= 1
    assert any(e["event"] == "scent.rejected" for e in seen)
