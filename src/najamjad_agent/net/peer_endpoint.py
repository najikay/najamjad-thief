"""Where to dial the opponent — from what they just told us, not from last week.

Every handshake carries the peer's own `identity.mcp_servers`, naming the URL
each of their roles is currently listening on. We logged it and dialled the URL
that had been typed into `network.opponent_url` before the match instead.

That is fine against a peer with a stable address and quietly fatal against one
without. uoh-sqak run **ngrok free, whose hostname re-mints every session** — a
fact already written on their own opponent card — so the moment they restart an
agent mid-series, the address we hold is dead and stays dead. Every send after
that fails, their access log shows nothing because our requests never reach
their server, and a TCP probe still succeeds because the ngrok *edge* answers on
any hostname whether or not a tunnel is behind it. Every symptom of the stall we
spent a week on, from one cached string.

**Which URL is the right one.** We need the endpoint for the role *they* are
playing, which is the opposite of ours: our police dials their thief. Getting
this backwards is silent — both keys usually exist and both usually resolve.

Deliberately conservative. A peer may only ever move us to an address **they**
declared inside a signed, hash-locked handshake; anything malformed, empty or
non-HTTP leaves us pointed where we were. An opponent who could redirect our
traffic by sending a string would be a much worse problem than a stale URL.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

#: Their role, given ours. They are always playing the other one.
OPPOSITE_ROLE = {"police": "thief", "cop": "thief", "thief": "police"}
#: Keys their declaration may use for the police endpoint, in preference order.
POLICE_KEYS = ("police", "cop")
THIEF_KEYS = ("thief",)


def _is_local(hostname: str) -> bool:
    """Whether a hostname names this machine or a private network.

    A peer choosing where our traffic goes is a peer who can choose *us*. Told
    to dial `http://127.0.0.1:8802/mcp` we would send our turns into our own
    inbox and read them back as theirs; pointed at an RFC1918 address we would
    spray the operator's LAN. Neither is a plausible place for an opponent's
    agent to be, so neither is worth accepting to be accommodating.

    Note this is a check on the *address they name*, not a resolution — a
    hostname that resolves to loopback still gets through, and stopping that
    would need a resolve on a path that must stay fast. It raises the bar from
    "any URL at all" to "an address that is at least plausibly theirs".
    """
    lowered = hostname.lower()
    if lowered in ("localhost", "ip6-localhost") or lowered.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return bool(
        address.is_loopback or address.is_private or address.is_link_local or address.is_reserved
    )


def _usable(url: Any) -> str:
    """A URL we are willing to dial, or empty string."""
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    if _is_local(parsed.hostname):
        return ""
    return text


def declared_endpoint(identity: dict[str, Any], our_role: str) -> str:
    """The URL the peer says it is serving on, for the role it is playing.

    Input: their handshake `identity` block and the role *we* hold.
    Output: a dialable URL, or empty string when they declared nothing usable.
    Setup: none — pure, so a replayed handshake resolves identically offline.
    """
    servers = identity.get("mcp_servers")
    if not isinstance(servers, dict):
        return ""
    their_role = OPPOSITE_ROLE.get(str(our_role).lower(), "")
    keys = POLICE_KEYS if their_role == "police" else THIEF_KEYS
    for key in keys:
        found = _usable(servers.get(key))
        if found:
            return found
    # A peer that declares exactly one server is telling us where it is,
    # whatever it labelled the key. uoh-sqak's handshake carries only `thief`
    # even in games where they are the police, and refusing to read a
    # single unambiguous address on a labelling technicality would cost us the
    # match to be pedantic about it.
    if len(servers) == 1:
        return _usable(next(iter(servers.values())))
    return ""


def _same_endpoint(one: str, other: str) -> bool:
    """Whether two URLs address the same host and path, ignoring cosmetics."""
    try:
        left, right = urlparse(one.strip()), urlparse(other.strip())
    except ValueError:
        return False
    return (
        (left.hostname or "").lower() == (right.hostname or "").lower()
        and left.path.rstrip("/") == right.path.rstrip("/")
    )


def is_our_own(url: str, ours: dict[str, Any] | None) -> bool:
    """Whether a peer just told us to dial an address **we** publish.

    Every other team in this league is running a fork of the reference, and
    several are running forks of *ours*. A peer who has not edited
    `[game.mcp_servers]` therefore declares our hostnames as its own, in perfect
    good faith — and we adopt them, because they are public, well-formed and
    not loopback, so `_usable` has no reason to object.

    The result is that we send every turn into our own tunnel. Measured against
    Amjad on 2026-08-06: the handshake locked correctly against his quick
    tunnel, his first turn arrived, and then we retargeted to
    `thief.4laboratory.com` — our own address, whose origin was not running —
    and burned the send budget on a 502 from our own edge before abandoning the
    mini-game. The fault log said `opponent-unreachable`, which was true of the
    address and deeply misleading about whose it was.

    Dialling ourselves cannot be correct under any circumstance, so this is a
    refusal rather than a preference: we keep the address the operator
    configured, which is the one that just completed a handshake.
    """
    if not ours:
        return False
    return any(_same_endpoint(url, str(mine)) for mine in ours.values() if mine)


def retarget(
    client: Any,
    identity: dict[str, Any],
    our_role: str,
    emit: Any = None,
    ours: dict[str, Any] | None = None,
) -> str:
    """Point `client` at the endpoint the peer just declared, if it moved.

    Input: the live `PeerClient`, their identity block, our role, and the
    endpoints *we* publish so a peer cannot send us to our own address.
    Output: the URL now in use.
    Setup: call once per sub-game, right after the handshake locks.

    A no-op when the address is unchanged, so the common case costs one string
    comparison and never disturbs a healthy held session.
    """
    publish = emit or (lambda _event: None)
    fresh = declared_endpoint(identity, our_role)
    current = str(getattr(client, "opponent_url", "") or "")
    if not fresh or fresh == current:
        return current
    if is_our_own(fresh, ours):
        # Loud, because the symptom without this line is a series of timeouts
        # against an address that looks like the opponent's in every log.
        publish({
            "event": "peer.declared_our_own_endpoint",
            "declared": fresh,
            "keeping": current,
            "our_role": our_role,
        })
        return current
    client.retarget(fresh)
    publish({"event": "peer.endpoint_moved", "was": current, "now": fresh, "our_role": our_role})
    return fresh
