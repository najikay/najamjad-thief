"""Our accumulated field against the kit's published walk, turn by turn.

Every scent test we had checked a *fresh* emission — one deposit on an empty
board — and our kernel was always right, so they all passed while the field we
actually transmitted was wrong from the second deposit onward. Our two repos
share this code, so cop and thief agreed with each other the whole time.

anrbj666's per-frame gate found it live on 2026-08-21: 34 of 35 frames refused
in one window, 33 of 35 in the next, and in each the single passing frame was
turn 1 — the only turn on which a max-merge and an addition agree.

Two faults, both ours:

* **the accumulation rule.** We merged with `max(tau, delta)` for both models.
  `multiplicative_book_v1` pins `tau' = clamp((1 - rho) * tau + delta, 0, 0.9)`
  in the document we declare the hash of. `(1 - rho) * tau` is the decay, which
  `decay_all` applies, so the deposit is `+ delta` and the clamp.
* **the wire precision.** `snapshot` rounded to three decimals, which is 5e-4 of
  error against a kit that publishes full IEEE-754 and recommends comparing at
  1e-6. Five hundred times the tolerance, on every cell, forever.

So this file walks the kit's own three turns and compares the whole field. A
fresh-emission test cannot fail either way, which is exactly how both survived.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.scent_models import ScentModel

KIT = Path(__file__).resolve().parents[2] / "fixtures" / "kit"
#: The tolerance anrbj666 gate at and the kit recommends, for the reason its own
#: ordering probe gives: two correct builds can differ in the last bit.
TOLERANCE = 1e-6


def walk() -> dict:
    return json.loads((KIT / "scent_book_v3.json").read_text(encoding="utf-8"))["field_walk"]


def field_after(turns: int) -> tuple[dict[str, float], dict[str, float]]:
    """Our field and the kit's, after `turns` turns of its published walk."""
    data = walk()
    scent = ScentField(board_size=data["board_size"], grid_size=5,
                       centre_intensity=data["center_intensity"],
                       decay=data["rho"], model=ScentModel.BOOK)
    for turn in data["turns"][:turns]:
        if turn["turn"] > 1:
            scent.decay_all()
        scent.deposit(tuple(turn["center"]))
    return scent.snapshot(), data["turns"][turns - 1]["field"]


@pytest.mark.parametrize("turn", [1, 2, 3])
def test_the_whole_field_matches_the_kit_walk(turn: int) -> None:
    """Turn 1 passed before this fix too — turns 2 and 3 are the test."""
    ours, theirs = field_after(turn)

    worst = max((abs(ours.get(cell, 0.0) - theirs.get(cell, 0.0))
                 for cell in set(ours) | set(theirs)), default=0.0)
    assert worst <= TOLERANCE, f"turn {turn}: worst cell error {worst:.2e}"


def test_a_second_deposit_adds_rather_than_taking_the_maximum() -> None:
    """The rule itself, isolated from the walk.

    Depositing twice on one cell must accumulate toward the ceiling. Under the
    old max-merge the second deposit changed nothing at all, which is precisely
    why a self-test between two identical builds could never notice.
    """
    scent = ScentField(board_size=7, grid_size=5, centre_intensity=0.9,
                       decay=0.1, model=ScentModel.BOOK)
    scent.deposit((3, 3))
    neighbour = scent.snapshot()["3,4"]

    scent.deposit((3, 4))

    assert scent.snapshot()["3,4"] > neighbour, "a second deposit must add"
    assert scent.snapshot()["3,4"] <= 0.9, "and must never exceed emit_intensity"


def test_the_subtractive_model_still_takes_the_maximum() -> None:
    """Only the book model changed. The kit publishes no accumulation vector for
    the subtractive one, ahk-yosi reported theirs is a max-merge identical to
    ours, and a stationary agent must plateau rather than climb."""
    scent = ScentField(board_size=7, grid_size=5, centre_intensity=0.9,
                       decay=0.1, model=ScentModel.REFERENCE)
    scent.deposit((3, 3))
    before = scent.snapshot()["3,3"]
    scent.deposit((3, 3))

    assert scent.snapshot()["3,3"] == before == 0.9


def test_the_wire_carries_full_precision() -> None:
    """Three decimals is 5e-4 of error against a 1e-6 gate."""
    scent = ScentField(board_size=7, grid_size=5, centre_intensity=0.9,
                       decay=0.1, model=ScentModel.BOOK)
    scent.deposit((3, 3))
    scent.decay_all()

    values = list(scent.snapshot().values())
    assert any(round(v, 3) != v for v in values), "a rounded grid cannot pass 1e-6"
