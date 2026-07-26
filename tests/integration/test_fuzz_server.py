"""Hostile payloads against the four public MCP tools (T-2119).

These endpoints face the open internet during a match, and every other team's
agent is a stranger's code. The contract is narrow and absolute: **never raise
at a peer, never crash, never enqueue something the game loop cannot handle.**
A structured rejection is always the right answer, because an exception escaping
here takes the server thread down and hands the match away.

Payloads are generated rather than listed, so the surface grows without anyone
remembering to extend a table.
"""

import random
import string

import pytest

from najamjad_agent.net.inbox import KINDS, Inboxes

TOOLS = sorted(KINDS)
HOSTILE_SCALARS = [
    None, True, 0, -1, 2**63, -(2**63), 3.5, float("inf"), float("nan"),
    "", " ", "\x00", "../../etc/passwd", "<script>alert(1)</script>",
    "'; DROP TABLE games; --", "{{7*7}}", "‮evil", "a" * 10_000,
]
HOSTILE_SHAPES = [
    {}, [], "not-an-object", 42, None,
    {"step": {"nested": "object"}},
    {"commit": ["list", "where", "string", "expected"]},
    {"smell_grid": "not-a-mapping"},
    {"smell_grid": {"0,0": "not-a-number"}},
    {"barrier_placed": [1, 2, 3, 4]},
    {"__proto__": {"polluted": True}},
    {"step": -5, "commit": "x" * 64},
]


@pytest.fixture()
def inboxes() -> Inboxes:
    """A fresh set of queues with events discarded."""
    return Inboxes()


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("payload", HOSTILE_SHAPES, ids=lambda p: str(p)[:28])
def test_a_hostile_shape_is_rejected_rather_than_raised(inboxes, tool, payload):
    """Any structural nonsense must produce a verdict, never an exception."""
    result = inboxes.accept(tool, payload)

    assert result.ok is False or result.model is not None
    if not result.ok:
        assert result.errors, "a rejection must say why"


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("value", HOSTILE_SCALARS, ids=lambda v: repr(v)[:24])
def test_a_hostile_scalar_in_any_field_never_crashes(inboxes, tool, value):
    """Every declared field gets the same nasty value in turn."""
    for field in ("step", "commit", "sender", "hint", "kind", "status"):
        result = inboxes.accept(tool, {field: value})

        assert isinstance(result.ok, bool), f"{tool}.{field} returned no verdict"


def test_an_unknown_tool_name_is_refused():
    """A peer inventing a verb must not reach any queue."""
    result = Inboxes().accept("drop_everything", {"step": 1})

    assert result.ok is False
    assert "unknown message kind" in result.errors[0]


def test_a_rejected_payload_never_lands_in_a_queue(inboxes):
    """The point of rejecting: the game loop must never see it."""
    for payload in HOSTILE_SHAPES:
        inboxes.accept("turn", payload)

    assert inboxes.poll("turn", timeout=0.01) is None


def test_a_flood_of_hostile_payloads_leaves_the_server_usable(inboxes):
    """Volume must not be a way to wedge us before a match."""
    rng = random.Random(11)
    for _ in range(2000):
        junk = {
            "".join(rng.choices(string.printable, k=6)): rng.choice(HOSTILE_SCALARS)
            for _ in range(4)
        }
        inboxes.accept(rng.choice(TOOLS), junk)

    healthy = inboxes.accept(
        "turn", {"step": 1, "sender": "thief", "commit": "b" * 64, "hint": "still here"}
    )

    assert healthy.ok is True, "a real turn must still be accepted after the flood"
