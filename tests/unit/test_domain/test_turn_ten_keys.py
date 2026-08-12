"""Every turn carries all ten keys, with unset optionals as explicit nulls.

The league's pinned wire shape spells a turn message as exactly ten keys. We
sent six and added the other four only on the turns where they occurred, which
is what the reference parser wants — but a peer that validates on *presence*
refuses a message whose optional is absent, and that refusal surfaces minutes
later as a turn timeout with no visible cause. Sending the key with a null
satisfies both readings at once.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.constants import Role
from najamjad_agent.domain.turn_egress import build_turn_message

TEN_KEYS = {
    "step", "sender", "hint", "smell_grid", "commit", "timestamp",
    "barrier_placed", "capture_claim", "claim_response", "win_claim",
}


class _State:
    """Only the three attributes `build_turn_message` reads."""

    def __init__(self, step: int = 4, role: Role = Role.THIEF) -> None:
        self.step = step
        self.role = role


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    return build_turn_message(_State(), commit="a" * 64, payload=payload)


def test_a_quiet_turn_still_carries_all_ten_keys() -> None:
    """The commonest turn of all: no barrier, no claim, nothing to declare."""
    message = _message({})

    assert set(message) == TEN_KEYS
    for optional in ("barrier_placed", "capture_claim", "claim_response", "win_claim"):
        assert message[optional] is None, f"{optional} must be an explicit null, not absent"


def test_we_never_emit_a_key_outside_the_ten() -> None:
    """The reference crashes on unknown keys, so extras in the payload stay out."""
    message = _message({"hint": "north", "smell_grid": {"3,3": 0.9},
                        "invented_field": "should not travel", "payload": {"secret": 1}})

    assert set(message) == TEN_KEYS
    assert message["hint"] == "north"
    assert message["smell_grid"] == {"3,3": 0.9}


def test_the_occurring_optionals_still_carry_their_values() -> None:
    """Nulls must not have flattened the fields that actually mean something."""
    message = _message({
        "barrier_placed": [2, 5],
        "capture_claim": (1, 1),
        "claim_response": {"claim": [1, 1], "caught": False},
        "win_claim": {"type": "survival"},
    })

    assert message["barrier_placed"] == [2, 5]
    # The claim IS the cell, and it travels as a list — a tuple would survive our
    # own round trip and arrive as a list through JSON, changing nothing we hash
    # but making our sent bytes differ from what we believed we sent.
    assert message["capture_claim"] == [1, 1]
    assert message["claim_response"] == {"claim": [1, 1], "caught": False}
    assert message["win_claim"] == {"type": "survival"}


def test_our_own_schema_accepts_what_we_now_send() -> None:
    """Ten keys with nulls must round-trip through our inbound parser."""
    from najamjad_agent.protocol.schemas_wire import TurnMessage

    parsed = TurnMessage.model_validate(_message({}))

    assert parsed.barrier_placed is None
    assert parsed.capture_claim is None
    assert parsed.step == 4
    assert parsed.sender == Role.THIEF.value
