"""Tests for the resolver cache that closed T-2456.

Three mini-games against uoh-sqak were lost to `[Errno -3] Temporary failure in
name resolution` on reconnect. The behaviour that matters is narrow: remember
what resolved, never remember what did not.
"""

import socket

import pytest

from najamjad_agent.net import dns_cache


@pytest.fixture(autouse=True)
def clean():
    dns_cache.uninstall()
    yield
    dns_cache.uninstall()


def test_a_repeated_lookup_only_hits_the_resolver_once() -> None:
    """The whole point: a reconnect must not re-query a name we already have."""
    calls: list[str] = []
    real = socket.getaddrinfo

    def counting(host, port, *args, **kwargs):
        calls.append(host)
        return real("localhost", port, *args, **kwargs)

    socket.getaddrinfo = counting
    try:
        dns_cache._original = None
        dns_cache.install()
        for _ in range(5):
            socket.getaddrinfo("opponent.example", 443)
    finally:
        dns_cache.uninstall()
        socket.getaddrinfo = real

    assert calls == ["opponent.example"], f"resolved {len(calls)} times, expected once"


def test_a_failure_is_never_cached() -> None:
    """A peer who is not up yet must stay reachable once they are.

    Caching a negative would turn "not started yet" into "permanently
    unreachable", which is worse than the bug being fixed.
    """
    attempts: list[str] = []
    real = socket.getaddrinfo

    def failing(host, port, *args, **kwargs):
        attempts.append(host)
        raise OSError(-3, "Temporary failure in name resolution")

    socket.getaddrinfo = failing
    try:
        dns_cache._original = None
        dns_cache.install()
        for _ in range(3):
            with pytest.raises(OSError):
                socket.getaddrinfo("down.example", 443)
    finally:
        dns_cache.uninstall()
        socket.getaddrinfo = real

    assert len(attempts) == 3, "a failed lookup must be retried, not remembered"


def test_installing_twice_does_not_wrap_the_wrapper() -> None:
    """Double-wrapping would make the real resolver unrecoverable."""
    real = socket.getaddrinfo

    assert dns_cache.install() is True
    assert dns_cache.install() is False
    dns_cache.uninstall()

    assert socket.getaddrinfo is real


def test_uninstall_restores_the_real_resolver() -> None:
    real = socket.getaddrinfo
    dns_cache.install()
    assert socket.getaddrinfo is not real

    dns_cache.uninstall()

    assert socket.getaddrinfo is real


def test_warming_a_reachable_host_reports_success() -> None:
    events: list[dict] = []
    dns_cache.install()

    assert dns_cache.warm("http://localhost:8802/mcp", emit=events.append) is True
    assert events[0]["event"] == "dns.warmed"


def test_warming_an_unresolvable_host_is_reported_not_raised() -> None:
    """The opponent may simply not be up yet; that is not our crash."""
    events: list[dict] = []
    dns_cache.install()

    assert dns_cache.warm("https://nx.invalid/mcp", emit=events.append) is False
    assert events[0]["event"] == "dns.warm_failed"


def test_a_url_without_a_host_warms_nothing() -> None:
    assert dns_cache.warm("", emit=None) is False
