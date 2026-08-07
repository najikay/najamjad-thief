"""We must dial where the opponent says they are, not where they used to be.

Every handshake carries the peer's `identity.mcp_servers`. We logged it and kept
dialling `network.opponent_url` from before the match — fine against a stable
address, quietly fatal against uoh-sqak, whose ngrok free hostname re-mints
every session. Once they restart an agent mid-series the address we hold is dead
and stays dead: their access log shows nothing (our requests never arrive), and
a TCP probe still succeeds (the ngrok edge answers on any hostname whether or
not a tunnel is behind it).
"""

import pytest

from najamjad_agent.net.peer_endpoint import declared_endpoint, retarget

THEIRS = {
    "mcp_servers": {
        "cop": "https://their-cop.ngrok-free.app/mcp",
        "thief": "https://their-thief.ngrok-free.app/mcp",
    }
}


class FakeClient:
    """A client that records where it was pointed, and when."""

    def __init__(self, url: str = "https://stale.ngrok-free.app/mcp") -> None:
        self.opponent_url = url
        self.retargets: list[str] = []

    def retarget(self, url: str) -> None:
        self.opponent_url = url
        self.retargets.append(url)


def test_our_police_dials_their_thief() -> None:
    """They are always playing the other role; getting this backwards is silent."""
    assert declared_endpoint(THEIRS, "police") == "https://their-thief.ngrok-free.app/mcp"


def test_our_thief_dials_their_police() -> None:
    assert declared_endpoint(THEIRS, "thief") == "https://their-cop.ngrok-free.app/mcp"


@pytest.mark.parametrize("alias", ["cop", "police"])
def test_either_spelling_of_the_police_key_is_accepted(alias: str) -> None:
    """Teams label it both ways; refusing one costs a match to be pedantic."""
    identity = {"mcp_servers": {alias: "https://theirs.example/mcp"}}

    assert declared_endpoint(identity, "thief") == "https://theirs.example/mcp"


def test_a_single_declared_server_is_used_whatever_its_label() -> None:
    """uoh-sqak's handshake carries only `thief`, in games where they are police.

    One unambiguous address is them telling us where they are. Refusing it on a
    labelling technicality would forfeit the game to win the argument.
    """
    identity = {"mcp_servers": {"thief": "https://only-one.ngrok-free.app/mcp"}}

    assert declared_endpoint(identity, "thief") == "https://only-one.ngrok-free.app/mcp"


def test_two_declared_servers_are_not_guessed_between() -> None:
    """Ambiguity must not be resolved by picking one; that is how you dial wrong."""
    identity = {"mcp_servers": {"alpha": "https://a.example/mcp", "beta": "https://b.example/mcp"}}

    assert declared_endpoint(identity, "police") == ""


@pytest.mark.parametrize(
    "servers",
    [
        {},
        {"thief": ""},
        {"thief": None},
        {"thief": "not-a-url"},
        {"thief": "ftp://elsewhere/mcp"},
        {"thief": "https:///mcp"},
    ],
)
def test_nothing_usable_leaves_us_pointed_where_we_were(servers: dict) -> None:
    """A peer must not be able to move us with a malformed string."""
    client = FakeClient()

    result = retarget(client, {"mcp_servers": servers}, "police")

    assert client.retargets == []
    assert result == "https://stale.ngrok-free.app/mcp"


def test_a_missing_mcp_servers_block_is_survivable() -> None:
    assert declared_endpoint({}, "police") == ""
    assert declared_endpoint({"mcp_servers": "not-a-dict"}, "police") == ""


def test_a_moved_endpoint_is_adopted_and_announced() -> None:
    """The fix, end to end."""
    client = FakeClient()
    events: list[dict] = []

    result = retarget(client, THEIRS, "police", events.append)

    assert result == "https://their-thief.ngrok-free.app/mcp"
    assert client.retargets == ["https://their-thief.ngrok-free.app/mcp"]
    assert events[0]["event"] == "peer.endpoint_moved"
    assert events[0]["was"] == "https://stale.ngrok-free.app/mcp"


def test_an_unchanged_endpoint_does_not_disturb_a_healthy_session() -> None:
    """The common case must cost one string comparison and no reconnect."""
    client = FakeClient("https://their-thief.ngrok-free.app/mcp")
    events: list[dict] = []

    retarget(client, THEIRS, "police", events.append)

    assert client.retargets == []
    assert events == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8802/mcp",
        "http://localhost:8802/mcp",
        "https://192.168.1.10/mcp",
        "http://10.0.0.5/mcp",
        "http://169.254.1.1/mcp",
        "http://[::1]:8802/mcp",
    ],
)
def test_a_peer_cannot_point_us_at_ourselves_or_the_local_network(url: str) -> None:
    """A peer choosing where our traffic goes is a peer who can choose *us*.

    Told to dial our own MCP port we would send turns into our own inbox and
    read them back as the opponent's; pointed at an RFC1918 address we would
    spray the operator's LAN. Our post-game audit payload goes down this same
    pipe, so the answer has to be no.
    """
    client = FakeClient()

    retarget(client, {"mcp_servers": {"thief": url}}, "police")

    assert client.retargets == [], f"accepted {url}"


def test_an_ordinary_public_endpoint_is_still_accepted() -> None:
    """The guard must not be so tight that a real opponent cannot move."""
    client = FakeClient()

    retarget(client, {"mcp_servers": {"thief": "https://abc123.ngrok-free.app/mcp"}}, "police")

    assert client.retargets == ["https://abc123.ngrok-free.app/mcp"]


class _Client:
    def __init__(self, url: str) -> None:
        self.opponent_url = url

    def retarget(self, url: str) -> None:
        self.opponent_url = url


OURS = {
    "cop": "https://cop.4laboratory.com/mcp",
    "thief": "https://thief.4laboratory.com/mcp",
}
AMJAD_URL = "https://circuit-voice-eastern-msgid.trycloudflare.com/mcp"


def test_a_peer_cannot_send_us_to_our_own_address() -> None:
    """The whole league is running forks, several of them forks of ours.

    A peer who has not edited `[game.mcp_servers]` declares our hostnames as
    its own in perfect good faith, and they are public, well-formed and not
    loopback — so nothing in `_usable` objects. We then post every turn into our
    own tunnel.

    Measured against Amjad on 2026-08-06: handshake locked against his quick
    tunnel, his first turn arrived, then we retargeted to
    `thief.4laboratory.com` — ours, with no origin running — and spent the send
    budget on a 502 from our own edge before abandoning the mini-game.
    """
    events: list[dict] = []
    client = _Client(AMJAD_URL)

    kept = retarget(client, {"mcp_servers": OURS}, "police", events.append, ours=OURS)

    assert kept == AMJAD_URL
    assert client.opponent_url == AMJAD_URL
    assert events[-1]["event"] == "peer.declared_our_own_endpoint"


def test_a_genuine_move_is_still_adopted() -> None:
    """The refusal must not cost us the case retargeting exists for.

    uoh-sqak's ngrok hostname re-mints every session; refusing all declarations
    would put us back to dialling a host nobody is behind.
    """
    events: list[dict] = []
    client = _Client(AMJAD_URL)
    moved = "https://their-new-tunnel.example.com/mcp"

    now = retarget(client, {"mcp_servers": {"thief": moved}}, "police", events.append, ours=OURS)

    assert now == moved
    assert events[-1]["event"] == "peer.endpoint_moved"


def test_the_match_is_on_host_and_path_not_spelling() -> None:
    """A trailing slash or capitalised host is the same address."""
    from najamjad_agent.net.peer_endpoint import is_our_own

    assert is_our_own("https://THIEF.4laboratory.com/mcp/", OURS)
    assert not is_our_own("https://thief.example.com/mcp", OURS)


def test_without_our_own_list_nothing_changes() -> None:
    """Every existing caller passes no `ours`, and must behave as before."""
    client = _Client(AMJAD_URL)
    moved = "https://somewhere-else.example.com/mcp"

    assert retarget(client, {"mcp_servers": {"thief": moved}}, "police") == moved
