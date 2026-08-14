"""A capture claim names the cop's own cell, and we were throwing it away.

Rules 21-22 make the claim mandatory and specific: the cop must name the cell it
asserts, because a thief who does not know where the cop is could not answer
honestly otherwise. That makes it the most precise position evidence this game
produces — an exact cell, disclosed under obligation, and truthful even when the
claim itself is a bluff.

`cop_sighting.from_claim` was written and tested for exactly this and **never
called**. Only `from_barrier` was wired, so we banked the weaker five-cell
inference and discarded the exact cell beside it. We parsed the claim to answer
it, stored it in `claimed_cell`, and never told the belief.

The peak stayed where diffusion left it no matter where the cop said it was.
"""

from __future__ import annotations

from najamjad_agent.constants import Role
from najamjad_agent.domain.turn_ingress import absorb_turn, decay_after_full_turn
from tests.fakes.orchestration import build_state


def _after_claim(claim: tuple[int, int] | None) -> tuple:
    """One absorbed turn as the thief, then the full-turn fusion."""
    state = build_state(Role.THIEF)
    message = {"step": 1, "sender": "police", "commit": "a" * 64, "smell_grid": {}}
    if claim is not None:
        message["capture_claim"] = list(claim)
    absorb_turn(state, message, lambda *_a, **_k: None)
    decay_after_full_turn(state)
    return state.belief.peak()


def test_a_claim_puts_the_belief_on_the_cell_the_cop_named() -> None:
    """The regression: this returned the diffusion peak whatever was claimed."""
    assert _after_claim((5, 5)) == (5, 5)
    assert _after_claim((0, 6)) == (0, 6)


def test_the_claim_is_what_moved_it_and_not_the_turn_itself() -> None:
    """Without a claim the peak must stay where diffusion put it, or the test
    above would pass against a belief that simply follows the last message."""
    bare = _after_claim(None)

    assert bare != (5, 5) and bare != (0, 6)


def test_a_claim_outranks_a_barrier_declared_the_same_turn() -> None:
    """The barrier says "within one step"; the claim says "here".

    `_record_sighting` prefers an exact sighting over an inexact one, so wiring
    the claim in must not let a five-cell reach displace an exact cell.
    """
    state = build_state(Role.THIEF)
    absorb_turn(state, {
        "step": 1, "sender": "police", "commit": "b" * 64, "smell_grid": {},
        "barrier_placed": [0, 1], "capture_claim": [5, 5],
    }, lambda *_a, **_k: None)
    decay_after_full_turn(state)

    assert state.belief.peak() == (5, 5), "the barrier's reach displaced the exact cell"


def test_a_malformed_claim_is_ignored_rather_than_fatal() -> None:
    """Everything here arrives from a competitor."""
    state = build_state(Role.THIEF)

    absorb_turn(state, {
        "step": 1, "sender": "police", "commit": "c" * 64, "capture_claim": "somewhere",
    }, lambda *_a, **_k: None)

    assert state.claimed_cell is None
