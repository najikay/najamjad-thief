"""What we declare at negotiate is derived from what we emit, not chosen beside it.

We run the book's model for the anrbj666 pairing. Switching it is one key in the
`pheromones` block of `config/game.json` — but the digest we declare used to be a
hardcoded constant, so setting that key without touching code would have had us
emitting the book field while declaring the Chebyshev one. Declaring a physics
we are not running is the precise fault removed from the scent-off path, and an
opponent who checks finds it at the audit rather than the handshake.

So the digest is looked up FROM the configured model. One source, no way to
disagree. `MODEL_DIGESTS` is the whole mechanism and this file is why it exists.

Both values are the kit's registrations, not our arithmetic:
`subtractive_chebyshev_v1` = 81ebee59..., `multiplicative_book_v1` = 934c220d...,
each reproduced from the registered document by `test_wire_shape_declaration`.
"""

from __future__ import annotations

import pytest

from najamjad_agent.domain.scent_models import ScentModel, decay_value, emission_field
from najamjad_agent.negotiation.contract import contract_hash
from najamjad_agent.negotiation.declarations import (
    BOOK_MODEL_SHA256,
    SCENT_MODEL_SHA256,
    negotiate_declarations,
)
from najamjad_agent.negotiation.terms import terms_from_config
from tests.role_config import load_role_config

#: The digest four teams have already re-derived and agreed with us.
AGREED_TERMS_SHA = "a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d"


class _Manager:
    """A stub that resolves dotted keys, because the real manager does.

    The first version stored `{"pheromones": {...}}` and answered
    `get("pheromones.pheromone_model")` with the default — so the book case
    "failed" against code that works. A double that cannot do what the real
    object does tests the double.
    """

    def __init__(self, model: str | None, scent: str = "full") -> None:
        pheromones = {"pheromone_grid_size": 5}
        if model is not None:
            pheromones["pheromone_model"] = model
        self._values = {"emission.scent": scent, "pheromones": pheromones,
                        "network.opponent_group_id": "anrbj666", "game.group_id": "najamjad"}

    def get(self, key, default=None):
        if key in self._values:
            return self._values[key]
        head, _, tail = key.partition(".")
        section = self._values.get(head)
        return section.get(tail, default) if tail and isinstance(section, dict) else default


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("book", BOOK_MODEL_SHA256), ("reference", SCENT_MODEL_SHA256),
     (None, SCENT_MODEL_SHA256), ("nonsense", SCENT_MODEL_SHA256)],
)
def test_the_digest_follows_the_configured_model(configured, expected) -> None:
    """Including the unreadable case: fall back, never invent a third answer."""
    declared = negotiate_declarations(_Manager(configured), {"board_size": 7}, "police", 1)

    assert declared["scent_model_sha256"] == expected


def test_the_shipped_config_declares_what_it_emits() -> None:
    """The live wiring, through the real loader — not a hand-built manager.

    Two ways to get this wrong, and this file has made both. `ConfigManager(path)`
    takes an already-merged mapping, so every lookup silently returns its default
    and the terms hash to something else entirely. And naming `config/police`
    passes here while failing in the thief repo, which ships `config/thief` —
    `tests/role_config` exists for precisely that, having been written the last
    time somebody did it.
    """
    manager = load_role_config()
    model = ScentModel(str(manager.get("pheromones", {}).get("pheromone_model", "reference")))
    declared = negotiate_declarations(manager, terms_from_config(manager), "police", 1)

    expected = {ScentModel.BOOK: BOOK_MODEL_SHA256, ScentModel.REFERENCE: SCENT_MODEL_SHA256}
    assert declared["scent_model_sha256"] == expected[model]


def test_choosing_a_model_never_moves_the_contract_hash() -> None:
    """The key rides in `pheromones`, which the signed extraction does not read.

    This is what makes the switch a config change rather than a re-negotiation:
    four teams have re-derived a284082d and agreed it, and none of them has to
    do it again because we changed which field we emit.
    """
    manager = load_role_config()
    terms = terms_from_config(manager)

    assert contract_hash(dict(terms)) == AGREED_TERMS_SHA
    assert "pheromone_model" not in terms


def test_the_two_models_are_actually_different_on_the_wire() -> None:
    """Otherwise none of the above would matter."""
    book = emission_field((3, 3), 0.9, 5, ScentModel.BOOK, 7)
    reference = emission_field((3, 3), 0.9, 5, ScentModel.REFERENCE, 7)

    assert book != reference
    assert book[(3, 4)] == 0.62 and reference[(3, 4)] == 0.6
    assert decay_value(0.9, 0.1, ScentModel.BOOK) == 0.81
    assert decay_value(0.9, 0.1, ScentModel.REFERENCE) == 0.8
