"""A handshake needs both agreements to cross, on whichever link works.

Three windows died against anrbj666 in one evening with the link healthy in the
direction that mattered. Their negotiates reached us 8-9 times a minute for ten
unbroken minutes while every call of ours to them timed out — so we held their
agreement, they never got ours, and neither side could start a window that both
sides wanted.

The exchange was two separate outbound calls, one per side. If either side's
outbound is down, it fails, even though a working connection existed the whole
time: theirs. So each side now answers a `negotiate` with its own agreement
attached, and reads the peer's from the reply to its own call. The handshake
completes over whichever direction happens to work.

Additive on the wire, and ignored by a peer that does not look for it — the
reference tolerates unknown response fields exactly as it tolerates unknown
request ones.
"""

import pytest

from najamjad_agent.negotiation.contract import Contract
from najamjad_agent.negotiation.handshake import HandshakeError, exchange_agreement

TERMS = {"board_size": 7, "num_games": 6}


def their_reply(terms: dict | None = None) -> dict:
    """An accepted negotiate whose body carries their signed agreement."""
    return {"accepted": True, "kind": "negotiate",
            "agreement": Contract(dict(terms or TERMS)).signed()}


def never_receive(_timeout):
    raise AssertionError("waited on an inbox when the reply already had it")


def test_their_agreement_is_taken_from_the_reply_to_our_call() -> None:
    """The case that completes when only OUR outbound works."""
    events: list[dict] = []

    peer = exchange_agreement(
        terms=TERMS, identity={}, send=lambda _p: their_reply(),
        receive=never_receive, emit=events.append,
    )

    assert peer["terms"] == TERMS
    names = [e["event"] for e in events]
    assert "handshake.agreement_in_reply" in names
    assert "handshake.locked" in names


def test_an_agreement_in_the_reply_is_verified_like_any_other() -> None:
    """In-band delivery is a transport shortcut, never a trust shortcut."""
    with pytest.raises(HandshakeError, match="different terms"):
        exchange_agreement(
            terms=TERMS, identity={},
            send=lambda _p: their_reply({"board_size": 9}), receive=never_receive,
        )


def test_a_reference_peer_that_answers_plainly_still_works() -> None:
    """Most of the class returns `{"accepted": true}` and nothing else."""
    peer = Contract(dict(TERMS)).signed()

    got = exchange_agreement(
        terms=TERMS, identity={},
        send=lambda _p: {"accepted": True, "kind": "negotiate"},
        receive=lambda _t: peer,
    )

    assert got["terms"] == TERMS


def test_a_junk_agreement_field_falls_back_to_the_inbox() -> None:
    """A peer using the key for something else must not break the handshake."""
    peer = Contract(dict(TERMS)).signed()

    for junk in ("yes", {"note": "hello"}, [], None, 7):
        got = exchange_agreement(
            terms=TERMS, identity={},
            send=lambda _p, j=junk: {"accepted": True, "agreement": j},
            receive=lambda _t: peer,
        )
        assert got["terms"] == TERMS


async def _call(boxes, tool: str, arguments: dict) -> dict:
    """Invoke one of our tools through a real MCP client, in memory.

    Through the protocol rather than by calling the function directly, for the
    same reason `test_interop_contract` does: the reply shape a peer actually
    receives is produced by the MCP layer, not by the handler alone.
    """
    import json

    from fastmcp import Client

    from najamjad_agent.net.mcp_server import build_server

    async with Client(build_server(boxes)) as client:
        result = await client.call_tool(tool, arguments)
        return json.loads(result.content[0].text) if result.content else {}


def _boxes(agreement: dict | None):
    from najamjad_agent.net.inbox import Inboxes

    boxes = Inboxes()
    boxes.our_agreement = agreement
    return boxes


@pytest.mark.asyncio
async def test_the_server_hands_our_agreement_back_on_their_negotiate() -> None:
    """The half that rescues a window when only THEIR outbound works."""
    ours = Contract(dict(TERMS)).signed()

    answer = await _call(_boxes(ours), "negotiate", {"message": Contract(dict(TERMS)).signed()})

    assert answer["accepted"] is True
    assert answer["agreement"]["terms"] == TERMS
    assert answer["agreement"]["signature"] == ours["signature"]


@pytest.mark.asyncio
async def test_nothing_is_attached_before_a_handshake_has_built_ours() -> None:
    """A bare listener has no agreement yet, and must not invent one."""
    answer = await _call(_boxes(None), "negotiate", {"message": Contract(dict(TERMS)).signed()})

    assert answer["accepted"] is True
    assert "agreement" not in answer


@pytest.mark.asyncio
async def test_a_turn_reply_never_carries_it() -> None:
    """Attaching it per step would put our terms on the wire 35 times a game."""
    answer = await _call(
        _boxes(Contract(dict(TERMS)).signed()),
        "receive_turn",
        {"message": {"step": 1, "commit": "a" * 16}},
    )

    assert "agreement" not in answer
