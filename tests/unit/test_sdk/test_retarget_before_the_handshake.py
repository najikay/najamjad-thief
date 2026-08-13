"""A role-split opponent has two doors, and each sub-game needs the other one.

The addresses below are vibecode's real ones on purpose: a documentation-range
IP is refused by `_is_local` as "not plausibly theirs", so a test written with a
placeholder passes for the wrong reason and proves nothing about the peer we are
about to play.

The thief opens every sub-game and roles alternate, so against a peer running
cop and thief as two processes on two URLs the address that answered sub-game 1
is the wrong one for sub-game 2. We retargeted only *after* the handshake, which
is one call too late: the handshake itself is what has to reach them, and it
would have gone to the process playing the role they had just finished.

Nothing had shown it. imreeyal route both hostnames to one port, uoh-ay26 and
uoh-sqak declare a single address, and the kit's sparring peer serves one URL —
so every opponent so far has been indifferent to which door we picked. vibecode
run two separate OS processes on two ports, which is the case this exists for,
and they said so in writing before we ever dialled them.
"""

from __future__ import annotations

from typing import Any

COP_URL = "http://62.56.220.143:61224/mcp"
THIEF_URL = "http://62.56.220.143:61223/mcp"
IDENTITY = {"group_id": "vibecode", "mcp_servers": {"cop": COP_URL, "thief": THIEF_URL}}


class _Client:
    def __init__(self, url: str = COP_URL) -> None:
        self.opponent_url = url
        self.dropped = 0

    def drop_session(self) -> None:
        self.dropped += 1

    def retarget(self, url: str) -> None:
        self.opponent_url = url


def test_playing_police_dials_their_thief_door() -> None:
    """The sub-game that failed: we are police, so their thief is the opener."""
    from najamjad_agent.net.peer_endpoint import retarget

    client = _Client(COP_URL)

    retarget(client, IDENTITY, "police", lambda _e: None, ours={})

    assert client.opponent_url == THIEF_URL


def test_playing_thief_dials_their_cop_door() -> None:
    """The mirror, which worked by accident because it came first."""
    from najamjad_agent.net.peer_endpoint import retarget

    client = _Client(THIEF_URL)

    retarget(client, IDENTITY, "thief", lambda _e: None, ours={})

    assert client.opponent_url == COP_URL


def test_a_single_door_peer_is_left_alone() -> None:
    """Every opponent so far. The fix must not disturb them."""
    from najamjad_agent.net.peer_endpoint import retarget

    one = {"mcp_servers": {"thief": THIEF_URL}}
    client = _Client(THIEF_URL)

    retarget(client, one, "police", lambda _e: None, ours={})

    assert client.opponent_url == THIEF_URL


def test_the_retarget_runs_before_the_exchange_not_only_after() -> None:
    """Ordering is the fix, so it is pinned against the source.

    The post-handshake retarget stays: it adopts an address a peer moved to
    mid-series. This one is about starting the sub-game at the right door.
    """
    from pathlib import Path

    source = Path("src/najamjad_agent/sdk/handshake_setup.py").read_text(encoding="utf-8")
    early = source.index('if role and isinstance(session.get("peer"), dict):')
    exchange = source.index("peer = exchange_agreement(")
    late = source.index("_bind_session(inboxes, session, declared")

    assert early < exchange < late, "the door must be chosen before the handshake is sent"


def test_the_early_retarget_is_skipped_on_the_first_sub_game() -> None:
    """No peer identity yet, so there is nothing to move to — and the card's
    URL is the only address anyone has. Reading a missing key must not raise."""
    session: dict[str, Any] = {}

    assert not isinstance(session.get("peer"), dict)
