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


# ------------------------------------------------- waiting long enough, loudly


def test_the_default_wait_allows_two_humans_to_coordinate():
    """120 s was the old default and it expired on a real match attempt.

    Two teams agreeing a time do not both start within two minutes: one is
    still reading a checklist, or their tunnel is still registering.
    """
    import inspect

    default = inspect.signature(opponent_wait.wait_for_opponent).parameters["timeout"].default

    assert default >= 600, "a wait shorter than ten minutes will expire on match day"


def test_waiting_is_reported_repeatedly_not_once(monkeypatch):
    """Fourteen silent minutes is indistinguishable from a hang.

    A single line at the start was right for a two-minute wait. At fifteen
    minutes an operator who suspects a hang restarts the process that was
    working — so the wait says so every minute, with how long is left.
    """
    monkeypatch.setattr(opponent_wait, "is_ready", lambda *_a, **_k: False)
    events: list[dict] = []
    now = [0.0]

    def clock() -> float:
        """Advances 30 s per read, so the poll loop crosses several notes."""
        now[0] += 30.0
        return now[0]

    opponent_wait.wait_for_opponent(
        "https://absent.invalid/mcp",
        timeout=300.0,
        emit=events.append,
        clock=clock,
        sleep=lambda _s: None,
    )

    waiting = [e for e in events if e["event"] == "opponent.waiting"]
    assert len(waiting) >= 2, "the wait must keep saying it is alive"
    assert "giving_up_in" in waiting[0], "and say how long is left"


def test_an_expired_wait_reports_absent_rather_than_ready(monkeypatch):
    """The caller depends on this answer to stop the match."""
    monkeypatch.setattr(opponent_wait, "is_ready", lambda *_a, **_k: False)
    now = [0.0]

    def clock() -> float:
        now[0] += 5.0
        return now[0]

    ready = opponent_wait.wait_for_opponent(
        "https://absent.invalid/mcp",
        timeout=10.0,
        emit=lambda _e: None,
        clock=clock,
        sleep=lambda _s: None,
    )

    assert ready is False
