"""A capture claim names the cop's own cell, and we spent three weeks not using it.

The claim must name a cell, because a thief who cannot see the cop could not
answer honestly otherwise. Which cell it names was the open question, and it was
settled by measuring the senders rather than by re-reading the receiver:

* both reference implementations send `list(rt.state.position)` whenever POLICE
  makes a move — their own position, on every move, not only on a landing;
* our own cop is locked to its own true cell by T-0535;
* **323 of 323** sealed claims across every archive in `matches/` name the
  claimer's own revealed position. `scripts/claim_evidence.py` re-runs it.

`cop_sighting.from_claim` was written and tested for exactly this and had no
caller through two attempts to give it one. Both removals were driven by an
argument from `answer_capture_claim(true_thief_cell, claimed_cell)` — which
cannot settle the question, because the answering line is identical whether the
cop is reporting its own cell or guessing at ours.

The belief peak stayed where diffusion left it no matter where the cop said it
was, on every turn of every series.
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


def test_a_claim_naming_our_own_cell_is_never_held() -> None:
    """The one attack that costs the opponent nothing, refused at the door.

    Our scent field hands them our exact cell every turn, so claiming it is free.
    Believed, it placed 0.99 on our square for the turn's closing `exclude()` to
    delete — and evicted whatever else that turn had told us on the way past.
    """
    state = build_state(Role.THIEF)
    seen = []
    absorb_turn(state, {
        "step": 1, "sender": "police", "commit": "d" * 64, "smell_grid": {},
        "capture_claim": list(state.own_position),
    }, lambda name, **fields: seen.append(name))

    assert state.cop_sighting is None
    assert "capture.claim_on_our_own_cell" in seen


def test_a_thief_peer_cannot_inject_a_sighting_with_a_claim() -> None:
    """Capture claims are police-only, so one from a thief is not a disclosure.

    Playing cop, our belief tracks the *thief*. A peer that answers our hunt with
    a `capture_claim` would be writing its own choice of cell straight into it,
    which is the opposite of evidence. `endings.py` already gates on the role and
    this mirrors that gate on the belief side.
    """
    state = build_state(Role.COP)
    before = state.belief.peak()
    absorb_turn(state, {
        "step": 1, "sender": "thief", "commit": "e" * 64, "smell_grid": {},
        "capture_claim": [6, 6],
    }, lambda *_a, **_k: None)
    decay_after_full_turn(state)

    assert state.belief.peak() != (6, 6), "a thief's claim reached our belief"
    assert before is not None


def test_a_malformed_claim_is_ignored_rather_than_fatal() -> None:
    """Everything here arrives from a competitor."""
    state = build_state(Role.THIEF)

    absorb_turn(state, {
        "step": 1, "sender": "police", "commit": "c" * 64, "capture_claim": "somewhere",
    }, lambda *_a, **_k: None)

    assert state.claimed_cell is None


def test_every_claim_is_kept_for_the_audit_to_check() -> None:
    """The measurement that keeps this sound has to keep being taken.

    Reading a claim as the cop's own cell is a fact about the peers we have met,
    not a guarantee the book gives. `verify_trail` compares each claim against
    the cell they reveal, so a peer that starts naming somewhere else is caught
    in our own archive rather than only in a later session's guesswork.
    """
    state = build_state(Role.THIEF)
    absorb_turn(state, {
        "step": 4, "sender": "police", "commit": "f" * 64, "capture_claim": [2, 5],
    }, lambda *_a, **_k: None)

    assert state.opponent_frames.claims == {4: (2, 5)}
