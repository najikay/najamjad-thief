"""Our acknowledgement answers to `ok` as well as `accepted`.

From the first match against uoh-ay26, 2026-08-07. Terms matched on all
fourteen signed fields, both servers were healthy, `handshake.locked` fired on
our side — and no game could start. Our server accepted their `negotiate` and
opened sub-game 1; their reference-derived client read the reply looking for
`ok`, could not find it, concluded we had rejected them, and re-sent.
Seventeen handshakes in three minutes, every one correctly refused with
"a mini-game is in progress", one turn sent by us and none received.

Nothing in that exchange was broken except a key name. We say `accepted`, the
reference says `ok`, and a peer that cannot see its own success key is
indistinguishable from a peer we turned away.

So we say both — the same trade `_body` already makes by accepting `message`
and `payload`. One extra key costs nothing and makes us the peer that works in
a league where most opponents are reference forks.

Driven through a real MCP client rather than by calling `_handle` directly,
because what the opponent actually parses is the serialised tool result, and
that is the only thing this test is about.
"""

import json

import pytest
from fastmcp import Client

from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.net.mcp_server import build_server

#: Enough of a negotiate body to be accepted; the shape is asserted elsewhere.
GOOD_NEGOTIATE = {
    "identity": "najamjad",
    "terms": {"grid_size": 7, "max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
    "nonce": "e" * 32,
    "signature": "f" * 64,
}


async def reply_to(body: dict) -> dict:
    """What a peer actually receives back from our `negotiate` tool."""
    async with Client(build_server(Inboxes())) as client:
        result = await client.call_tool("negotiate", {"message": body})
        return json.loads(result.content[0].text) if result.content else {}


@pytest.mark.asyncio
async def test_an_accepted_message_says_so_under_both_names() -> None:
    """A reference client reads `ok`, ours reads `accepted`; both must see yes."""
    reply = await reply_to(GOOD_NEGOTIATE)

    assert reply["accepted"] is True
    assert reply["ok"] is True, "a reference-derived client reads `ok` and would re-send without it"


@pytest.mark.asyncio
async def test_a_rejected_message_says_so_under_both_names() -> None:
    """And both must see no.

    This is the half worth arguing for: an absent `ok` is falsy, so a client
    checking only `ok` reads a *missing* key and a deliberate refusal
    identically, and never reaches the `errors` list that says which term was
    wrong.
    """
    reply = await reply_to({"identity": "najamjad"})  # no terms, nonce or signature

    assert reply["accepted"] is False
    assert reply["ok"] is False
    assert reply["errors"], "a refusal that names no reason cannot be acted on"


@pytest.mark.asyncio
async def test_the_two_keys_never_disagree() -> None:
    """The pair is the contract: either key alone must reach the same verdict."""
    for body in (GOOD_NEGOTIATE, {"identity": "najamjad"}):
        reply = await reply_to(body)

        assert reply["ok"] == reply["accepted"], f"keys disagree for {sorted(body)}"
