"""Waiting for the opponent to actually be there (T-2430).

Both peers dial each other and neither controls who is ready first, so a wait
exists. It was a plain TCP probe, and that was wrong in the one configuration
every real match uses: behind a tunnel.

A Cloudflare edge accepts TCP on :443 whether or not the agent behind it is
running — a dead origin is only visible as `502` at the HTTP layer. So the wait
returned True instantly against an opponent who was not there, and the first
handshake died with `502 Bad Gateway`. Found by it happening.
"""

from najamjad_agent.net import opponent_wait

# ------------------------------------------------- readiness through a tunnel


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_a_tunnel_edge_answering_for_a_dead_agent_is_not_ready(monkeypatch):
    """The defect this suite existed to prevent, and did not.

    Cloudflare accepts TCP on :443 whether or not the agent behind it is
    running; a dead origin only shows up as `502` at the HTTP layer. The TCP
    probe therefore returned True instantly against an opponent who was not
    there, the wait passed, and the first handshake died with 502 Bad Gateway —
    in exactly the tunnelled configuration every real match uses.
    """
    monkeypatch.setattr("httpx.post", lambda *_a, **_k: Response(502))

    assert opponent_wait.answers_http("https://tunnel.invalid/mcp") is False


def test_a_protocol_refusal_counts_as_ready(monkeypatch):
    """`400 Missing session ID` is their MCP server talking to us.

    Readiness means "someone is home", not "someone agreed". Treating a 4xx as
    down would leave us waiting out the clock on a healthy opponent.
    """
    monkeypatch.setattr("httpx.post", lambda *_a, **_k: Response(400))

    assert opponent_wait.answers_http("https://tunnel.invalid/mcp") is True


def test_a_transport_failure_is_not_ready(monkeypatch):
    def explode(*_a, **_k):
        raise OSError("no route to host")

    monkeypatch.setattr("httpx.post", explode)

    assert opponent_wait.answers_http("https://tunnel.invalid/mcp") is False


def test_an_http_url_is_probed_over_http_not_tcp(monkeypatch):
    """The routing decision itself: a tunnelled URL must not fall back to TCP."""
    monkeypatch.setattr(opponent_wait, "is_listening", lambda *_a, **_k: True)
    monkeypatch.setattr(opponent_wait, "answers_http", lambda *_a, **_k: False)

    assert opponent_wait.is_ready("https://tunnel.invalid/mcp", "tunnel.invalid", 443) is False


def test_a_bare_host_and_port_still_uses_the_tcp_probe(monkeypatch):
    """Exact for a direct target, and the only check available for one."""
    monkeypatch.setattr(opponent_wait, "is_listening", lambda *_a, **_k: True)

    assert opponent_wait.is_ready("127.0.0.1:8801", "127.0.0.1", 8801) is True
