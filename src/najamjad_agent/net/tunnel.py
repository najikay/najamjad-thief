"""Public exposure via a tunnel with a **permanent** hostname.

Assignment 6's single most expensive defect: quick tunnels mint a new random
hostname on every restart, so the opponent's URL kept changing and the URLs
persisted into versioned config went stale. The fix is structural — the public
hostname is read from configuration and never scraped from the process output,
so a restart cannot change it (FR-NET-3, ADR-004).

Named tunnels (Cloudflare) are the default; ngrok with a reserved static domain
is a config-only switch, no code change. The child process is always spawned
with an argument list — never a shell — so a hostname from config cannot become
a command-injection path.
"""

import shutil
import subprocess
import threading
from collections.abc import Callable
from typing import Any

from ..shared.events import Emit

PROVIDERS = ("cloudflare", "ngrok")


class TunnelError(Exception):
    """Raised when the tunnel cannot be configured or started."""


def build_command(provider: str, hostname: str, port: int, name: str = "") -> list[str]:
    """The argument list that exposes `port` at the agreed `hostname`."""
    if provider == "cloudflare":
        if not name:
            raise TunnelError("cloudflare requires a named tunnel (tunnel.name)")
        return ["cloudflared", "tunnel", "run", "--url", f"http://127.0.0.1:{port}", name]
    if provider == "ngrok":
        return ["ngrok", "http", str(port), "--domain", hostname, "--log", "stdout"]
    raise TunnelError(f"unknown tunnel provider {provider!r}; expected one of {PROVIDERS}")


class Tunnel:
    """Supervises the tunnel process and reports its health."""

    def __init__(
        self,
        provider: str,
        hostname: str,
        port: int,
        name: str = "",
        emit: Emit | None = None,
        spawn: Callable[[list[str]], Any] | None = None,
    ) -> None:
        """Configure the tunnel; nothing runs until `start()`."""
        if provider not in PROVIDERS:
            raise TunnelError(f"unknown tunnel provider {provider!r}; expected one of {PROVIDERS}")
        if not hostname:
            raise TunnelError("tunnel.hostname must be set — a changing URL breaks every peer")
        self.provider = provider
        self.hostname = hostname
        self.port = port
        self.name = name
        self._emit = emit or (lambda _event: None)
        self._spawn = spawn or self._default_spawn
        self._process: Any = None
        self._restarts = 0
        self._lock = threading.Lock()

    @property
    def public_url(self) -> str:
        """The MCP endpoint we hand to opponents — stable across restarts."""
        return f"https://{self.hostname}/mcp"

    @property
    def restarts(self) -> int:
        """How many times the supervisor has revived the process."""
        return self._restarts

    @staticmethod
    def _default_spawn(command: list[str]) -> Any:
        """Launch the tunnel binary (argument list; never a shell)."""
        if shutil.which(command[0]) is None:
            raise TunnelError(
                f"{command[0]} is not installed or not on PATH — see docs/runbook-network.md"
            )
        return subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no interpolation
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def command(self) -> list[str]:
        """The exact argument list this tunnel will run."""
        return build_command(self.provider, self.hostname, self.port, self.name)

    def start(self) -> None:
        """Start the tunnel process (idempotent)."""
        with self._lock:
            if self.alive():
                return
            self._process = self._spawn(self.command())
        self._emit({"event": "tunnel.up", "provider": self.provider, "url": self.public_url})

    def alive(self) -> bool:
        """True while the tunnel process is running."""
        return self._process is not None and self._process.poll() is None

    def check(self) -> bool:
        """Restart the tunnel if it has exited; returns True when a restart ran."""
        if self._process is None or self.alive():
            return False
        code = self._process.poll()
        self._emit({"event": "tunnel.down", "provider": self.provider, "exit_code": code})
        self._restarts += 1
        self._process = self._spawn(self.command())
        self._emit({"event": "tunnel.restarted", "url": self.public_url, "restarts": self._restarts})
        return True

    def stop(self) -> None:
        """Terminate the tunnel process (idempotent)."""
        with self._lock:
            process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        self._emit({"event": "tunnel.stopped", "provider": self.provider})


def from_config(config: Any, port: int, emit: Emit | None = None) -> Tunnel:
    """Build a tunnel from the `[tunnel]` config table (provider switch, no code)."""
    return Tunnel(
        provider=str(config.get("tunnel.provider", "cloudflare")),
        hostname=str(config.require("tunnel.hostname")),
        port=port,
        name=str(config.get("tunnel.name", "")),
        emit=emit,
    )
