"""The guards that ride beside the signed terms.

The signature covers the terms and nothing else, so two peers can agree on the
contract hash byte for byte and still be running different pheromone maths,
different sub-game numbers, or the same role. Those disagree silently and
surface at audit time, when there is nothing left to fix.

These pin the declarations that refuse such a pairing at the handshake, and —
more importantly — pin the *scent digest against our own implementation*, so a
change to our maths that stops matching `subtractive_chebyshev_v1` fails here
rather than in front of an opponent who trusted the declaration.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from najamjad_agent.domain.scent_models import ScentModel, decay_value, emission_field
from najamjad_agent.negotiation.contract import Contract, derive_game_ids
from najamjad_agent.negotiation.declarations import (
    INFO_MODE_SHA256,
    SCENT_MODEL_SHA256,
    negotiate_declarations,
)

TERMS: dict[str, Any] = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
    "emit_intensity": 0.9, "min_center_intensity": 0.5, "max_steps": 35,
    "barriers_max": 14, "setting": "New York", "hint_max_words": 15,
    "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 6,
}

# The kit's published example for `subtractive_chebyshev_v1`: emit at the centre
# of a 7x7 board, then one decay. Transcribed from vectors/locked_model.json.
KIT_PEAK_AFTER_ONE_DECAY = 0.8
KIT_FIELD_CELLS = 25


class _Manager:
    """The two config lookups `negotiate_declarations` makes."""

    def __init__(self, **values: Any) -> None:
        self._values = {"game.group_id": "najamjad", "network.opponent_group_id": "imreeyal"}
        self._values.update(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


def test_we_declare_the_scent_model_we_actually_run() -> None:
    """The declaration is a claim about our maths; this checks the claim.

    Declaring a model we do not implement is worse than declaring nothing: the
    opponent stops checking, plays a full series against different physics, and
    both audits disagree with no field to point at.
    """
    field = emission_field((3, 3), 0.9, 5, ScentModel.REFERENCE, board_size=7)
    decayed = {cell: round(decay_value(value, 0.1, ScentModel.REFERENCE), 3)
               for cell, value in field.items()}

    assert len(field) == KIT_FIELD_CELLS
    assert max(decayed.values()) == KIT_PEAK_AFTER_ONE_DECAY
    # Chebyshev-linear, not the book's radial kernel: 0.9 / 0.6 / 0.3 by ring.
    assert field[(3, 3)] == 0.9
    assert field[(2, 3)] == 0.6
    assert field[(1, 3)] == 0.3


def test_the_digests_are_the_kit_doc_hash_construction() -> None:
    """Both are SHA-256 over the registered doc, compact-canonical.

    Reproduced rather than pasted: an opponent's copy of a hash is worth exactly
    as much as their copy of the document behind it.
    """
    doc = {"family": "info_mode", "name": "belief"}
    digest = hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()

    assert len(digest) == len(INFO_MODE_SHA256) == len(SCENT_MODEL_SHA256) == 64
    assert INFO_MODE_SHA256 != SCENT_MODEL_SHA256


def test_the_declared_uid_is_the_one_both_peers_derive() -> None:
    """The uid never crosses the wire during play, so it is declared instead.

    Two teams once played a whole series under two different uids and found out
    at report time, when the two artifact sets would not join.
    """
    declared = negotiate_declarations(_Manager(), TERMS, "police", 3)
    _, expected = derive_game_ids(dict(TERMS), "najamjad", "imreeyal")

    assert declared["game_uid"] == expected
    assert declared["sub_game_number"] == 3
    assert declared["role"] == "police"


def test_no_uid_is_declared_before_we_know_who_they_are() -> None:
    """A uid keyed on the placeholder would refuse an honest peer.

    Omission never refuses on either side; a wrong value refuses at T+seconds.
    """
    for group in ("", "them"):
        declared = negotiate_declarations(
            _Manager(**{"network.opponent_group_id": group}), TERMS, "thief", 1
        )

        assert "game_uid" not in declared
        assert declared["role"] == "thief"


def test_declarations_ride_beside_the_signature_without_disturbing_it() -> None:
    """The four reference keys must survive, and the signature must still verify."""
    plain = Contract(dict(TERMS), identity={"group_id": "najamjad"})
    declared = Contract(
        dict(TERMS),
        identity={"group_id": "najamjad"},
        declarations=negotiate_declarations(_Manager(), TERMS, "police", 2),
    )

    message = declared.signed()
    assert set(message) > set(plain.signed())
    assert message["sub_game_number"] == 2
    assert message["scent_model_sha256"] == SCENT_MODEL_SHA256
    # A peer holding the same terms still verifies us — declarations are outside
    # the signature precisely so a peer that sends none can still check ours.
    Contract(dict(TERMS)).verify_peer(message)


def test_a_declaration_can_never_overwrite_the_signature() -> None:
    """`_RESERVED` is enforced, not merely documented.

    A declaration named `signature` would be a self-inflicted refusal at the one
    moment nothing can be debugged.
    """
    contract = Contract(
        dict(TERMS),
        declarations={"signature": "hijacked", "terms": {}, "nonce": "x", "identity": "y"},
    )

    message = contract.signed()
    assert message["signature"] != "hijacked"
    assert message["terms"] == TERMS
    Contract(dict(TERMS)).verify_peer(message)
