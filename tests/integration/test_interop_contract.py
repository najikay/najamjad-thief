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
