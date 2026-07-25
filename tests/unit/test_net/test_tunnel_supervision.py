"""Tests for tunnel supervision: restart on exit, shutdown, and config wiring."""

import pytest

from najamjad_agent.net.tunnel import PROVIDERS, Tunnel, TunnelError, build_command


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


def test_a_dead_tunnel_is_detected_and_restarted() -> None:
    events: list[dict] = []
    tunnel, spawner = _tunnel(events)
    tunnel.start()
    tunnel._process.exit_code = 137
    assert tunnel.check()
    assert tunnel.restarts == 1
    assert len(spawner.commands) == 2
    names = [event["event"] for event in events]
    assert "tunnel.down" in names and "tunnel.restarted" in names


def test_a_healthy_tunnel_is_left_alone() -> None:
    tunnel, spawner = _tunnel()
    tunnel.start()
    assert not tunnel.check()
    assert len(spawner.commands) == 1


def test_check_before_start_does_nothing() -> None:
    tunnel, spawner = _tunnel()
    assert not tunnel.check()
    assert spawner.commands == []


def test_stop_terminates_and_is_idempotent() -> None:
    events: list[dict] = []
    tunnel, spawner = _tunnel(events)
    tunnel.start()
    process = spawner.processes[0]
    tunnel.stop()
    tunnel.stop()
    assert process.terminated
    assert any(event["event"] == "tunnel.stopped" for event in events)


def test_stop_kills_a_process_that_refuses_to_terminate() -> None:
    tunnel, spawner = _tunnel()
    tunnel.start()
    process = spawner.processes[0]

    def stubborn_wait(timeout: float | None = None) -> int:
        import subprocess

        raise subprocess.TimeoutExpired(cmd="cloudflared", timeout=timeout or 0)

    process.wait = stubborn_wait  # type: ignore[method-assign]
    process.terminate = lambda: None  # type: ignore[method-assign]
    tunnel.stop()
    assert process.killed


def test_providers_are_the_two_book_recommended_tools() -> None:
    assert set(PROVIDERS) == {"cloudflare", "ngrok"}


def test_from_config_reads_the_tunnel_table() -> None:
    """Provider selection is configuration, never a code change (ADR-004)."""
    from najamjad_agent.net.tunnel import from_config

    class StubConfig:
        def get(self, key, default=None):
            return {"tunnel.provider": "ngrok"}.get(key, default)

        def require(self, key):
            return "cop.ngrok.app"

    tunnel = from_config(StubConfig(), port=8802)
    assert tunnel.provider == "ngrok"
    assert tunnel.public_url == "https://cop.ngrok.app/mcp"


def test_a_missing_tunnel_binary_gives_an_actionable_error() -> None:
    """Point at the runbook rather than a raw FileNotFoundError."""

    from najamjad_agent.net.tunnel import Tunnel

    real = Tunnel(provider="cloudflare", hostname="h.example", port=8802, name="t")
    with pytest.raises(TunnelError, match="runbook-network"):
        real._default_spawn(["definitely-not-installed-binary", "run"])


def test_ngrok_command_shape_is_covered() -> None:

    assert build_command("ngrok", "h.ngrok.app", 1234)[:3] == ["ngrok", "http", "1234"]


def test_build_command_rejects_an_unknown_provider() -> None:

    from najamjad_agent.net.tunnel import build_command

    with pytest.raises(TunnelError, match="unknown tunnel provider"):
        build_command("quick", "h", 1)


def test_the_real_spawn_launches_an_installed_binary(monkeypatch) -> None:
    """Covers the production spawn path without starting a real tunnel."""
    from najamjad_agent.net import tunnel as tunnel_module

    launched: list[list[str]] = []

    class DummyPopen:
        def __init__(self, command, **kwargs):
            launched.append(command)
            self.kwargs = kwargs

        def poll(self):
            return None

    monkeypatch.setattr(tunnel_module.shutil, "which", lambda _name: "/usr/bin/echo")
    monkeypatch.setattr(tunnel_module.subprocess, "Popen", DummyPopen)

    real = Tunnel(provider="ngrok", hostname="h.ngrok.app", port=8802)
    process = real._default_spawn(real.command())

    assert launched[0][0] == "ngrok"
    assert "shell" not in process.kwargs, "a shell would be a command-injection path"
