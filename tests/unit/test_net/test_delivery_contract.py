"""The kit's own §7.1 decision table, run against our implementation.

Vendored from `github.com/Imreec/copthief-league-protocol`, `vectors/
delivery_contract.json`, rather than restated here in our words. A table
paraphrased into a test is a table that can drift from the one an opponent
implements, and we would not find out until a live redelivery — which is the
kind of discovery that scores zero for both teams under App. E rule 35.

The gap this closes was real but latent. `TurnSequence` deduped on the step and
refused everything at or below the last accepted one, so a redelivery and a
forged step produced the same refusal. `inbox.out_of_order` had fired zero
times across every match we have logged, so nothing had ever exercised it — a
guard that has only ever seen well-behaved traffic, which is exactly the
condition this project has been bitten by before.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from najamjad_agent.net.delivery import REORDER_WINDOW, decide

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "kit" / "delivery_contract.json"


def kit() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _state(raw: dict) -> tuple[dict[int, str], int, int]:
    """The fixture's state shape, in the ints our function takes."""
    played = {int(step): commit for step, commit in raw["played"].items()}
    return played, int(raw["next"]), int(raw["window"])


@pytest.mark.parametrize("case", kit()["arrivals"], ids=lambda c: c["decision"])
def test_every_arrival_decides_as_the_kit_says(case) -> None:
    """All six decisions, from their fixture, through our function."""
    played, nxt, window = _state(kit()["state"])
    arrival = case["arrival"]

    got = decide(played, nxt, int(arrival["step"]), arrival["commit"], window)

    assert got == case["decision"], case.get("note", "")


def test_a_zero_window_receiver_is_the_failure_they_name() -> None:
    """Pinned so nobody 'tightens' the window back to zero.

    The kit calls this out specifically: a receiver with no reorder window turns
    an ordinary retry race into a protocol violation, and zero tolerance is not
    a tightening a strict peer may choose.
    """
    case = kit()["no_reorder_window"]
    played, nxt, _ = _state(case["state"])
    arrival = case["arrival"]

    got = decide(played, nxt, int(arrival["step"]), arrival["commit"],
                 int(case["state"]["window"]))

    assert got == case["decision"] == "violation"
    assert REORDER_WINDOW > 0, "our shipped window must not be the dangerous one"


def test_redelivery_and_equivocation_are_told_apart() -> None:
    """The distinction the old step-only guard could not make at all."""
    played, nxt, window = {1: "c1", 2: "c2"}, 3, REORDER_WINDOW

    assert decide(played, nxt, 2, "c2", window) == "absorb"
    assert decide(played, nxt, 2, "forged", window) == "equivocation"


def test_the_fixture_is_the_published_one() -> None:
    """A vendored fixture that quietly diverges proves nothing."""
    data = kit()

    assert data["status"] == "PROMOTED"
    assert {a["decision"] for a in data["arrivals"]} == {
        "apply", "absorb", "equivocation", "buffer", "violation", "discard"
    }
