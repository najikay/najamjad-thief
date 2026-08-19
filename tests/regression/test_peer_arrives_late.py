"""The anrbj666 failure, reproduced: outbound dead, inbound alive, peer late.

Three fixes passed their unit tests and then failed against this peer three
evenings running, which is the whole argument for this file. The doubles those
tests used were kinder than the opponent in the one way that mattered: they
answered. This one does not.

The shape, taken from our event log of 2026-08-19:

* our calls to their door raise — every one, for the whole window;
* their calls to ours succeed — 8-9 a minute, once their window opens;
* and their window opens *late*, because they run one peer process per window
  and it does not exist while the previous mini-game is still being played.

Nothing here is mocked at the seam being tested. The inbox is the real
`Inboxes`, the server is the real one built by `build_server`, and the peer
reaches it through a real in-memory MCP client — because the reply body is
produced by the MCP layer, and the reply body is now half the handshake.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import Client

from najamjad_agent.negotiation.contract import Contract
from najamjad_agent.negotiation.handshake import exchange_agreement
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.mcp_server import build_server

TERMS = {"board_size": 7, "num_games": 6}
OURS = {"sub_game_number": 4, "role": "police"}


def dead_outbound(_payload):
    """Their door, as ours saw it for ten unbroken minutes."""
    raise ConnectionError("All connection attempts failed")


async def peer_dials_us(boxes: Inboxes) -> dict:
    """Their window opens and the first thing it does is call us."""
    theirs = {**Contract(dict(TERMS)).signed(), "sub_game_number": 4}
    async with Client(build_server(boxes)) as client:
        result = await client.call_tool("negotiate", {"message": theirs})
        return json.loads(result.content[0].text) if result.content else {}


@pytest.mark.asyncio
async def test_the_window_starts_on_their_knock_with_our_outbound_dead() -> None:
    """The whole point: no call of ours succeeds, and the window still opens."""
    boxes = Inboxes()
    boxes.our_agreement = Contract(dict(TERMS)).signed()

    reply = await peer_dials_us(boxes)

    # Their call carried our agreement home — the direction that always worked.
    assert reply["accepted"] is True
    assert reply["agreement"]["terms"] == TERMS
    assert boxes.agreement_sent == 1

    # And their agreement is now here for us, without us reaching them at all.
    events: list[dict] = []
    peer = exchange_agreement(
        terms=TERMS, identity={}, declarations=dict(OURS),
        send=dead_outbound,
        receive=lambda timeout: _as_dict(boxes.poll("negotiate", timeout=timeout)),
        emit=events.append,
    )

    assert peer["terms"] == TERMS
    assert "handshake.locked" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_nothing_is_lost_while_the_peer_has_not_spawned_yet() -> None:
    """Before their window opens there is no door, and we must not invent one."""
    boxes = Inboxes()
    boxes.our_agreement = Contract(dict(TERMS)).signed()

    with pytest.raises(ConnectionError):
        exchange_agreement(
            terms=TERMS, identity={}, declarations=dict(OURS),
            send=dead_outbound,
            receive=lambda _t: None,          # nobody there yet
        )

    # The next attempt must still find them when they do arrive.
    reply = await peer_dials_us(boxes)
    assert reply["agreement"]["terms"] == TERMS

    peer = exchange_agreement(
        terms=TERMS, identity={}, declarations=dict(OURS),
        send=dead_outbound,
        receive=lambda timeout: _as_dict(boxes.poll("negotiate", timeout=timeout)),
    )
    assert peer["terms"] == TERMS


def _as_dict(message):
    """The inbox hands back a pydantic model; the handshake indexes a mapping."""
    if message is None:
        return None
    return message.model_dump() if hasattr(message, "model_dump") else dict(message)
