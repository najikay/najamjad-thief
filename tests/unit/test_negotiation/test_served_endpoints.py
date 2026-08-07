"""Declare where we are, not where a differently-configured sibling would be.

`[game.mcp_servers]` names two permanent hostnames, one per role. But **one
match is one process on one port** — roles alternate within a series, and the
same agent plays both. So in the mini-games where we held the other role we were
publishing a hostname with nothing behind it, and an opponent that honours the
label dials it and gets a 502 for half the series.

That is not hypothetical: `net/peer_endpoint` records it happening in reverse on
2026-08-06, when a peer's fork declared *our* hostnames and we posted a whole
mini-game into our own dead tunnel. Every fork of this repo has the same
config, so both directions are live.

The reference has always pointed both role keys at the same port.
"""


from najamjad_agent.negotiation.identity import served_endpoints
from najamjad_agent.net.peer_endpoint import is_our_own
from najamjad_agent.shared.config import ConfigManager
from tests.role_config import load_role_config


def test_both_role_keys_name_the_one_endpoint_we_serve() -> None:
    """A peer dialling either key reaches a process that is actually listening."""
    servers = served_endpoints(load_role_config())

    assert set(servers) == {"cop", "thief"}
    assert servers["cop"] == servers["thief"]


def test_a_tunnelless_run_advertises_something_reachable() -> None:
    """`--no-tunnel` rehearsals must not publish a hostname that does not exist."""
    manager = ConfigManager({"network": {"my_port": 8802}})

    servers = served_endpoints(manager)

    assert servers["cop"] == "http://127.0.0.1:8802/mcp"


def test_the_tunnel_hostname_wins_when_there_is_one() -> None:
    manager = ConfigManager(
        {"network": {"my_port": 8802}, "tunnel": {"hostname": "cop.example.com"}}
    )

    assert served_endpoints(manager)["thief"] == "https://cop.example.com/mcp"


def test_the_self_dial_guard_still_covers_the_sibling() -> None:
    """The pairing that makes this safe, and the way it could quietly break.

    We now advertise one address — so if `is_our_own` took its list from what we
    *advertise*, it would stop recognising the sibling hostname, and a peer
    running our config could still send us there. The guard reads the
    **configured** pair; the declaration reads the served one. Narrowing one
    must never narrow the other.
    """
    manager = load_role_config()
    configured = dict(manager.get("game.mcp_servers", {}) or {})
    advertised = served_endpoints(manager)

    assert len(set(configured.values())) == 2, "the config still names two hostnames"
    for url in configured.values():
        assert is_our_own(url, configured), f"{url} is ours and must be refused"
    assert not is_our_own("https://a-real-opponent.example/mcp", configured)
    assert len(set(advertised.values())) == 1, "we advertise only what we serve"


def test_the_identity_actually_uses_it() -> None:
    """The seam — the assertions above pass while `identity` publishes the old pair."""
    import inspect

    from najamjad_agent.negotiation import identity

    assert "served_endpoints(manager)" in inspect.getsource(identity.identity_from_config)
