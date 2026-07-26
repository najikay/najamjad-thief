"""The wire contract we share with every other team (T-2111).

The reference implementation names the tool argument `message` on three tools
and `payload` on `submit_audit`, and its client sends exactly that. We sent
`payload` everywhere, and accepted only `payload` — so against any agent built
on the reference (most of the class) *nothing worked in either direction*: they
could not deliver a turn to us and we could not deliver one to them. Verified
against the real simulator, before and after.

The rule these tests encode: **send exactly what the reference declares, accept
either name.** Conservative out, liberal in — the peer that works.
"""

import json

import pytest
from fastmcp import Client

from najamjad_agent.constants import Move, Role
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.mcp_client import ARGUMENT_FOR_TOOL, TOOL_FOR_KIND
from najamjad_agent.net.mcp_server import build_server

# Taken from the reference implementation's own client and server:
#   client: call_tool(tool, {"message": arg} if tool != "submit_audit" else {"payload": arg})
#   server: negotiate(message), receive_turn(message), submit_audit(payload),
#           receive_control(message)
REFERENCE_ARGUMENT = {
    "negotiate": "message",
    "receive_turn": "message",
    "submit_audit": "payload",
    "receive_control": "message",
}
TURN = {"step": 1, "sender": "thief", "commit": "d" * 64, "hint": "hi", "smell_grid": {}}
NEGOTIATE = {
    "identity": "najamjad",
    "terms": {"grid_size": 7, "max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
    "nonce": "e" * 32,
    "signature": "f" * 64,
}
BODIES = {"submit_audit": {"records": []}, "receive_control": {"kind": "status"},
          "negotiate": NEGOTIATE, "receive_turn": TURN}


async def call_tool(tool: str, arguments: dict) -> dict:
    """Invoke one of our tools through a real MCP client, in memory.

    Through the protocol rather than by calling the function directly: the bug
    this file exists for lived in argument *binding*, which only the MCP layer
    performs.
    """
    async with Client(build_server(Inboxes())) as client:
        result = await client.call_tool(tool, arguments)
        return json.loads(result.content[0].text) if result.content else {}


async def tool_names() -> set[str]:
    """Every tool we expose."""
    async with Client(build_server(Inboxes())) as client:
        return {tool.name for tool in await client.list_tools()}


@pytest.mark.parametrize(("tool", "expected"), sorted(REFERENCE_ARGUMENT.items()))
def test_we_send_the_argument_name_the_reference_declares(tool, expected):
    """Sending `payload` to `receive_turn` is rejected outright by a reference
    peer — this mapping is not ours to choose."""
    assert ARGUMENT_FOR_TOOL[tool] == expected


def test_every_kind_we_can_send_has_an_argument_mapping():
    """A kind without a mapping would silently fall back and fail on the wire."""
    for tool in TOOL_FOR_KIND.values():
        assert tool in ARGUMENT_FOR_TOOL, f"{tool} would be sent with a guessed argument name"


@pytest.mark.asyncio
async def test_we_expose_exactly_the_four_mandated_tools():
    assert await tool_names() == set(REFERENCE_ARGUMENT)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(REFERENCE_ARGUMENT))
@pytest.mark.parametrize("argument", ["message", "payload"])
async def test_our_server_accepts_either_argument_name(tool, argument):
    """Liberal in what we accept: a peer using either convention gets through."""
    response = await call_tool(tool, {argument: dict(BODIES[tool])})

    assert response.get("accepted") is True, f"{tool} refused a valid {argument} call"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(REFERENCE_ARGUMENT))
async def test_a_call_with_neither_argument_is_refused_not_crashed(tool):
    """A peer sending nothing at all still gets a verdict, never a stack."""
    response = await call_tool(tool, {})

    assert response.get("accepted") is False


# The reference's TurnMessage dataclass, transcribed from its own source. Its
# parser does `cls(**data)`, so a field it does not declare is a TypeError —
# sending one extra key makes every turn we send unreadable to it.
REFERENCE_TURN_FIELDS = {
    "step", "sender", "hint", "smell_grid", "commit", "timestamp",
    "barrier_placed", "capture_claim", "claim_response", "win_claim",
}
REFERENCE_TURN_REQUIRED = {"step", "sender", "hint", "smell_grid", "commit", "timestamp"}


def built_turn(role: Role, **kwargs) -> dict:
    """A turn message produced by the real orchestrator."""
    from tests.fakes.orchestration import build_orchestrator

    orchestrator, transport, _ = build_orchestrator(role=role, **kwargs)
    orchestrator.take_turn()
    return transport.sent[0]


def test_our_turn_carries_every_field_the_reference_requires():
    """`timestamp` was missing, and its parser treats that as fatal."""
    message = built_turn(Role.COP, moves=[Move.SOUTH])

    assert set(message) >= REFERENCE_TURN_REQUIRED, (
        f"missing {sorted(REFERENCE_TURN_REQUIRED - set(message))}"
    )


@pytest.mark.parametrize("role", [Role.COP, Role.THIEF])
def test_we_never_send_a_field_the_reference_cannot_parse(role):
    """Its parser rejects unknown keys outright, so our vocabulary must be a
    subset of its own — `claimed_cell` used to break exactly this."""
    message = built_turn(role, moves=[Move.SOUTH])

    assert set(message) <= REFERENCE_TURN_FIELDS, (
        f"we send {sorted(set(message) - REFERENCE_TURN_FIELDS)}, which it declares no field for"
    )


def test_a_capture_claim_is_sent_as_the_claimed_cell():
    """The reference reads `capture_claim` as [r, c], not as a boolean."""
    orchestrator, transport, _ = _claiming_cop()

    claim = transport.sent[0]["capture_claim"]

    assert isinstance(claim, list) and len(claim) == 2
    assert claim == list(orchestrator.state.own_position)


def test_a_claim_answer_is_sent_in_the_reference_shape():
    from tests.fakes.orchestration import build_orchestrator

    orchestrator, transport, _ = build_orchestrator(
        role=Role.THIEF, position=(3, 3), moves=[Move.STAY]
    )
    orchestrator._transport.inbox.append(
        {"step": 1, "sender": "police", "commit": "a" * 64, "capture_claim": [3, 3]}
    )
    orchestrator.receive_turn()
    orchestrator.take_turn()

    assert transport.sent[-1]["claim_response"] == {"claim": [3, 3], "caught": True}


def _claiming_cop():
    from tests.fakes.orchestration import build_orchestrator

    orchestrator, transport, brain = build_orchestrator(role=Role.COP, moves=[Move.STAY])
    orchestrator.state.opponent_estimate = orchestrator.state.own_position
    orchestrator.take_turn()
    return orchestrator, transport, brain
