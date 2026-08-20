"""We declare the wire shape we actually implement, and can prove the digest.

The kit registers two wire shapes and they are not interchangeable.
`reference-v3` is four tools, one message per half-turn, the smell grid on the
wire, the move revealed at audit — us. `bookletter-v3` is two messages per
half-turn, revealed per half-turn, and no grid on the wire at all. Two peers on
different shapes agree on every signed term, lock cleanly, and then each waits
for messages the other was never going to send.

anrbj666 declared `wire_shape_sha256` at us and we filed it under
`inbox.unknown_fields`. Omission never refuses, so nothing broke — we were
simply declining a guard that was being handed to us, in a pairing that spent
three evenings on exactly the class of fault this catches.

The digest is **recomputed from the registered document**, not pasted. A pasted
constant proves only that someone once copied a string correctly; recomputing it
with our own canonical encoder proves our §2 serialization still matches the one
every other hash in this league depends on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from najamjad_agent.negotiation.declarations import (
    INFO_MODE_SHA256,
    SCENT_MODEL_SHA256,
    WIRE_SHAPE_SHA256,
    negotiate_declarations,
)
from najamjad_agent.protocol.canonical import canonical_json

LOCKED = Path(__file__).resolve().parents[2] / "fixtures" / "kit" / "locked_model.json"


class _Manager:
    def __init__(self, scent: str = "full") -> None:
        self._values = {"emission.scent": scent, "network.opponent_group_id": "them-real",
                        "game.group_id": "najamjad"}

    def get(self, key, default=None):
        return self._values.get(key, default)


def registered() -> dict[str, dict]:
    """The kit's registered documents, keyed `family:name`."""
    data = json.loads(LOCKED.read_text(encoding="utf-8"))
    return {f"{e['doc']['family']}:{e['doc']['name']}": e for e in data["registered"]}


def digest_of(doc: dict) -> str:
    return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()


def test_we_recompute_every_digest_we_declare() -> None:
    """Our canonical form must reproduce the kit's, or nothing else holds."""
    docs = registered()

    assert digest_of(docs["wire_shape:reference-v3"]["doc"]) == WIRE_SHAPE_SHA256
    assert digest_of(docs["scent_model:subtractive_chebyshev_v1"]["doc"]) == SCENT_MODEL_SHA256
    assert digest_of(docs["info_mode:belief"]["doc"]) == INFO_MODE_SHA256


def test_the_shape_we_declare_is_the_one_we_implement() -> None:
    """Declaring a shape we do not run would be worse than declaring none."""
    params = registered()["wire_shape:reference-v3"]["doc"]["params"]

    assert params["tools"] == ["negotiate", "receive_turn", "submit_audit", "receive_control"]
    assert params["messages_per_half_turn"] == 1
    assert params["smell_grid_on_wire"] is True
    assert params["move_revealed"] == "at_audit"


def test_the_other_registered_shape_is_the_one_we_would_refuse() -> None:
    """Pinned so the value of declaring is visible, not just asserted."""
    other = registered()["wire_shape:bookletter-v3"]["doc"]["params"]

    assert other["messages_per_half_turn"] == 2
    assert other["smell_grid_on_wire"] is False
    assert digest_of(registered()["wire_shape:bookletter-v3"]["doc"]) != WIRE_SHAPE_SHA256


def test_it_rides_the_negotiate_extras() -> None:
    """Top-level beside the other declarations, never inside `terms`."""
    declared = negotiate_declarations(_Manager(), {"board_size": 7}, "police", 3)

    assert declared["wire_shape_sha256"] == WIRE_SHAPE_SHA256


def test_silence_drops_the_scent_claim_and_keeps_the_wire_shape() -> None:
    """The wire shape is true whatever we emit; the scent model is not."""
    declared = negotiate_declarations(_Manager("none"), {"board_size": 7}, "thief", 2)

    assert "scent_model_sha256" not in declared
    assert declared["wire_shape_sha256"] == WIRE_SHAPE_SHA256
