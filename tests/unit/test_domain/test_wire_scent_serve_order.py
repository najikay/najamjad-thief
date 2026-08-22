"""The frames on the wire ARE the kit's published walk, for both roles.

`test_scent_matches_the_kit_walk` proves the field *maths* is bit-exact. It
cannot see the seam this file pins: **which snapshot the orchestrator samples
for the wire.** The kit's `field_walk` (anrbj666 co-author it) transmits
decayed-prior-plus-fresh-deposit — its turn 2 reads 0.036 at a cell an
undecayed trail gives as 0.04.

Until 2026-08-22 we decayed our own field in `decay_after_full_turn`, after
the send. That put the two roles on *different* conventions: the cop
(receive → decay → deposit → send) happened to match the kit; the thief
(deposit → send → … → decay) transmitted every trail cell one decay step too
fresh. anrbj666's per-frame gate refused 34 of 35 of our thief's frames over
it, while both sides' peaks read 0.9 throughout — which is why no digest and
no peak log ever caught it. So this file drives the *orchestrator*, not the
field, through the walk's own three turns and compares every frame that
crossed the fake wire against the kit's published field, cell for cell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from najamjad_agent.constants import Move, Role
from tests.fakes.orchestration import build_orchestrator

KIT = Path(__file__).resolve().parents[2] / "fixtures" / "kit"
TOLERANCE = 1e-6
#: The walk's centres are (3,3), (3,4), (2,4); a deposit lands on the cell we
#: occupy after the move, so STAY/EAST/NORTH from (3,3) reproduces them.
WALK_MOVES = [Move.STAY, Move.EAST, Move.NORTH]


def _walk() -> list[dict]:
    data = json.loads((KIT / "scent_book_v3.json").read_text(encoding="utf-8"))
    return data["field_walk"]["turns"]


def _turn(step: int) -> dict:
    return {"step": step, "sender": "police", "commit": f"{step:064x}",
            "smell_grid": {}, "hint": ""}


def _frames(role: Role) -> list[dict]:
    orchestrator, transport, _ = build_orchestrator(
        role=role, moves=list(WALK_MOVES),
        inbox=[_turn(1), _turn(2), _turn(3)], position=(3, 3),
    )
    for _ in range(3):
        if role is Role.COP:
            orchestrator.receive_turn()
            orchestrator.take_turn()
        else:
            orchestrator.take_turn()
            orchestrator.receive_turn()
    return [message["smell_grid"] for message in transport.sent]


def _worst_error(ours: dict, theirs: dict) -> float:
    cells = set(ours) | set(theirs)
    return max((abs(float(ours.get(c, 0.0)) - float(theirs.get(c, 0.0)))
                for c in cells), default=0.0)


def test_the_thief_transmits_the_kit_walk_frame_for_frame() -> None:
    """The direction their gate measured: the thief moves first, then sends."""
    frames = _frames(Role.THIEF)

    for sent, published in zip(frames, _walk(), strict=True):
        worst = _worst_error(sent, published["field"])
        assert worst <= TOLERANCE, (
            f"turn {published['turn']}: worst cell error {worst:.2e} — "
            "the wire is not the walk"
        )


def test_the_cop_transmits_the_identical_frames() -> None:
    """Role symmetry: the same deposits produce the same wire, receive-first
    or send-first. This is the asymmetry the old placement created."""
    assert _frames(Role.COP) == _frames(Role.THIEF)


def test_the_reference_model_rides_the_same_serve_order() -> None:
    """The kit publishes a walk only for the book model, so the reference
    model's serve order is pinned by hand: age the prior (subtractive, -0.1),
    then merge the fresh rings by max. The trail cell the fresh kernel cannot
    re-saturate is the witness — 0.8 aged, where the stale wire read 0.9."""
    from najamjad_agent.domain.scent import ScentField
    from najamjad_agent.domain.scent_models import ScentModel

    field = ScentField(board_size=7, model=ScentModel.REFERENCE)
    field.age_and_deposit((3, 3))
    assert field.snapshot()["3,3"] == pytest.approx(0.9)

    field.age_and_deposit((3, 4))
    frame = field.snapshot()
    assert frame["3,4"] == pytest.approx(0.9), "the fresh deposit is undecayed"
    # (3,3): aged 0.9 -> 0.8, and the new ring-1 value 0.6 loses the max-merge.
    assert frame["3,3"] == pytest.approx(0.8), "the trail ages before transmit"
    # (3,1): held ring-2 (0.3) aged to 0.2, and it sits chebyshev-3 from the
    # new centre — outside the 5x5 kernel — so the aged value IS the wire.
    assert frame["3,1"] == pytest.approx(0.2)
    # (3,2): held ring-1 (0.6) aged to 0.5 beats the fresh ring-2 (0.3) under
    # the reference's max-merge — unlike the book's additive clamp.
    assert frame["3,2"] == pytest.approx(0.5)
