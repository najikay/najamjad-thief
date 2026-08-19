"""A model we are not running is not a model we may declare.

anrbj666, 2026-08-19, proposed a mutually-silent arrangement: both sides send
`smell_grid: {}` and neither declares a scent model. Legal for us — `none` is a
documented emission mode — but `negotiate_declarations` sent
`scent_model_sha256` unconditionally, so we would have declared a field nobody
was putting on the wire.

Two reasons that matters, and the second is the expensive one. It is untrue: the
declaration exists so both sides can refuse a physics mismatch before play, and
a claim about an unused model cannot be checked against anything. And their spec
refuses on a declared *mismatch* while omission never refuses, so declaring
under silence is the one thing most likely to refuse an honest peer at the
handshake — for a field neither of us would have sent.
"""

from typing import Any

from najamjad_agent.negotiation.declarations import (
    SCENT_MODEL_SHA256,
    negotiate_declarations,
)

TERMS = {"board_size": 7, "num_games": 6}


class _Manager:
    """Just enough config to answer the two keys the function reads."""

    def __init__(self, scent: str) -> None:
        self._values: dict[str, Any] = {
            "emission.scent": scent,
            "network.opponent_group_id": "anrbj666",
            "game.group_id": "najamjad",
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


def test_we_declare_the_model_while_we_are_emitting() -> None:
    """The ordinary case, unchanged: emission and declaration agree."""
    declared = negotiate_declarations(_Manager("full"), TERMS, "police", 1)

    assert declared["scent_model_sha256"] == SCENT_MODEL_SHA256


def test_a_window_emission_still_declares() -> None:
    """`window` is a narrower field, not a different physics."""
    assert "scent_model_sha256" in negotiate_declarations(_Manager("window"), TERMS, "thief", 2)


def test_silence_declares_no_model_at_all() -> None:
    """The case anrbj666 asked for; omission never refuses an honest peer."""
    declared = negotiate_declarations(_Manager("none"), TERMS, "police", 3)

    assert "scent_model_sha256" not in declared


def test_silence_leaves_every_other_guard_in_place() -> None:
    """Only the scent claim goes. The window number is what stops one game
    acquiring two `sub_game_number`s, and it is needed most when we are quiet."""
    declared = negotiate_declarations(_Manager("none"), TERMS, "police", 3)

    assert declared["sub_game_number"] == 3
    assert declared["role"] == "police"
    assert "info_mode_sha256" in declared
    assert "game_uid" in declared


def test_an_unset_mode_declares_as_before() -> None:
    """A config without the key is an emitting config; absence must not silence."""
    assert "scent_model_sha256" in negotiate_declarations(_Manager(""), TERMS, "thief", 4)
