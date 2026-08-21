"""The outbound session must be replaced before each sub-game's handshake.

A peer may run every sub-game as its own process — the league's pinned wire
shape asks for it, and imreeyal implement it. The socket we hold through game N
is attached to a process that no longer exists when game N+1 opens, so reusing
it dials a corpse: nothing refuses, the call simply hangs until our per-call cap
fires.

The failure is invisible from outside, which is what made it expensive. A bare
`curl` opens a new connection and reads a healthy 406 off the peer's *new*
process while our client times out against the old one — so the tunnel looks
fine and the peer looks fine. It cost a whole friendly on 2026-08-12: every one
of 49 failures was a read timeout at exactly the 10 s cap, not one
`client.session_opened` was emitted after the first sub-game settled, and three
attempts landed inside a window the peer's new process was provably bound and
answering.
"""

from __future__ import annotations

from typing import Any


class _Session:
    """Stands in for the held MCP session."""

    def __init__(self, url: str, emit: Any = None) -> None:
        self.url = url
        self.connected = True
        self.dropped = False


def test_dropping_replaces_the_session_object(monkeypatch) -> None:
    """The next call must open a new session, not reuse the released one."""
    from najamjad_agent.net import mcp_client

    monkeypatch.setattr(mcp_client, "PeerSession", _Session)
    client = mcp_client.PeerClient(opponent_url="https://peer.example/mcp", gatekeeper=None)
    first = client._session
    monkeypatch.setattr(client, "_release_session", lambda: None)

    client.drop_session()

    assert client._session is not first, "a dropped session must be replaced"
    assert client._session.url == "https://peer.example/mcp"


def test_dropping_twice_is_harmless(monkeypatch) -> None:
    """Idempotent: the second drop has nothing to drop and must not raise."""
    from najamjad_agent.net import mcp_client

    monkeypatch.setattr(mcp_client, "PeerSession", _Session)
    client = mcp_client.PeerClient(opponent_url="https://peer.example/mcp", gatekeeper=None)
    monkeypatch.setattr(client, "_release_session", lambda: None)

    client.drop_session()
    client._session.connected = False
    client.drop_session()


def test_the_transport_drops_the_client_session() -> None:
    """`new_session` is the transport-level name for the same thing."""
    from najamjad_agent.net.peer_transport import PeerTransport

    calls: list[str] = []

    class _Client:
        def drop_session(self) -> None:
            calls.append("dropped")

    transport = PeerTransport(inboxes=object(), client=_Client(), deadlines=object())
    transport.new_session()

    assert calls == ["dropped"]


def test_the_session_is_dropped_before_the_handshake_not_after() -> None:
    """Ordering is the whole fix.

    The handshake is the first call of a sub-game, so a session replaced *after*
    it is replaced one call too late — which is exactly what the old code did:
    `reset()` ran inside the sub-game, well past the point the handshake had
    already burned its attempts against a dead socket.
    """
    from pathlib import Path

    source = Path("src/najamjad_agent/domain/match.py").read_text(encoding="utf-8")
    new_session = source.index("self._transport.new_session()")
    handshake = source.index("if not agree_on_terms(")
    reset = source.index("self._transport.reset(sub_game)")

    assert new_session < handshake, "the session must be fresh before the handshake"
    assert handshake < reset, "reset stays after the handshake; it drops queued inbound"
