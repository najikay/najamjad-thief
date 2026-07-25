"""Tests for tunnel supervision — above all, that the public URL never changes."""

import pytest

from najamjad_agent.net.tunnel import Tunnel, TunnelError, build_command


class FakeProcess:
    """A tunnel binary we can kill and revive on demand."""

    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


class Spawner:
    """Records every launch so we can assert on the argv."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.processes: list[FakeProcess] = []

    def __call__(self, command: list[str]) -> FakeProcess:
        self.commands.append(command)
        process = FakeProcess()
        self.processes.append(process)
        return process


def _tunnel(events: list[dict] | None = None, **overrides) -> tuple[Tunnel, Spawner]:
    spawner = Spawner()
    settings = {
        "provider": "cloudflare",
        "hostname": "cop.najamjad.dev",
        "port": 8802,
        "name": "najamjad-cop",
        **overrides,
    }
    tunnel = Tunnel(
        emit=(events.append if events is not None else None), spawn=spawner, **settings
    )
    return tunnel, spawner


def test_public_url_comes_from_config_not_from_process_output() -> None:
    """A6 pain #3: quick tunnels mint a new hostname on every restart."""
    tunnel, _ = _tunnel()
    assert tunnel.public_url == "https://cop.najamjad.dev/mcp"


def test_the_url_is_identical_after_a_restart() -> None:
    """The whole point: an opponent's saved URL keeps working."""
    tunnel, _ = _tunnel()
    tunnel.start()
    before = tunnel.public_url
    tunnel._process.exit_code = 1
    tunnel.check()
    assert tunnel.public_url == before


def test_a_missing_hostname_is_refused_at_construction() -> None:
    with pytest.raises(TunnelError, match="changing URL breaks every peer"):
        Tunnel(provider="cloudflare", hostname="", port=8802, name="x")


def test_unknown_provider_is_refused() -> None:
    with pytest.raises(TunnelError, match="unknown tunnel provider"):
        Tunnel(provider="quicktunnel", hostname="h", port=1)


def test_cloudflare_command_runs_a_named_tunnel() -> None:
    """Named, not quick — quick tunnels are what caused the churn."""
    command = build_command("cloudflare", "cop.najamjad.dev", 8802, "najamjad-cop")
    assert command[:3] == ["cloudflared", "tunnel", "run"]
    assert "najamjad-cop" in command
    assert "http://127.0.0.1:8802" in command


def test_cloudflare_without_a_tunnel_name_is_refused() -> None:
    with pytest.raises(TunnelError, match="named tunnel"):
        build_command("cloudflare", "host", 8802, "")


def test_ngrok_fallback_uses_a_reserved_static_domain() -> None:
    """ADR-004 fallback: a config switch, never a code change."""
    command = build_command("ngrok", "cop.ngrok.app", 8802)
    assert command[0] == "ngrok"
    assert "--domain" in command
    assert "cop.ngrok.app" in command


def test_switching_provider_needs_no_code_change() -> None:
    cloudflare, spawner_a = _tunnel()
    ngrok, spawner_b = _tunnel(provider="ngrok", hostname="cop.ngrok.app")
    cloudflare.start()
    ngrok.start()
    assert spawner_a.commands[0][0] == "cloudflared"
    assert spawner_b.commands[0][0] == "ngrok"


def test_the_process_is_never_launched_through_a_shell() -> None:
    """A hostname from config must not be able to become a command."""
    tunnel, spawner = _tunnel(hostname="evil.example; rm -rf /")
    tunnel.start()
    assert isinstance(spawner.commands[0], list)
    assert all(isinstance(part, str) for part in spawner.commands[0])


def test_start_is_idempotent() -> None:
    tunnel, spawner = _tunnel()
    tunnel.start()
    tunnel.start()
    assert len(spawner.commands) == 1


def test_start_emits_an_up_event() -> None:
    events: list[dict] = []
    tunnel, _ = _tunnel(events)
    tunnel.start()
    assert events[0]["event"] == "tunnel.up"
    assert events[0]["url"] == tunnel.public_url
