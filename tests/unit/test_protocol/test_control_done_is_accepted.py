"""A peer announcing the end of a sub-game must not be told it is malformed.

vibecode send `control{kind: "done"}` once at the close of every sub-game. Our
schema validated `kind` against a closed set that did not include it, so all six
of the 2026-08-14 series were refused with `unknown control kind 'done'` — a
peer politely marking a boundary and being answered with a validation error.

Nothing broke, because the boundary is also visible in the audit exchange. That
is exactly what makes it the kind of interop gap that goes unnoticed until the
day it is the only signal, and rejecting a well-formed message from a peer who
is doing nothing wrong is the shape of fault our adapter layer exists to absorb.

Accepting an informational verb is not the same as guessing at one: the list
stays closed, and a genuinely unknown verb is still refused.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from najamjad_agent.protocol.schemas_wire import ControlMessage


def test_done_is_accepted() -> None:
    """The regression, in the exact shape they send it."""
    assert ControlMessage(kind="done").kind == "done"


@pytest.mark.parametrize("kind", ["enable", "status", "restart", "quit"])
def test_the_verbs_we_act_on_still_parse(kind: str) -> None:
    assert ControlMessage(kind=kind).kind == kind


def test_a_genuinely_unknown_verb_is_still_refused() -> None:
    """The list stays closed. Widening it to anything at all would make the
    validator decorative, and the point of refusing is that we do not guess at
    a verb we cannot implement."""
    with pytest.raises(ValidationError) as caught:
        ControlMessage(kind="self_destruct")

    assert "unknown control kind" in str(caught.value)


def test_done_carries_no_action() -> None:
    """It is informational, and must stay that way.

    `done` is queued and never consumed as an instruction — the control queue
    is opt-in behind `features.controls` and nothing in the match path reads a
    verb from it. A peer must not be able to end our process by announcing a
    boundary, so this pins that `done` looks nothing like `quit`.
    """
    message = ControlMessage(kind="done")

    assert message.status == ""
    assert message.step_budget is None
