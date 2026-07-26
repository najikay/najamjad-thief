"""The composition root: build a wired SDK from configuration on disk.

Somewhere has to know how the pieces fit together. Putting that in the CLI
would give the CLI business knowledge it is forbidden to have, and putting it in
the SDK facade would make the facade construct things instead of delegate. So it
lives here — one function the CLI calls and the SDK exposes.

Which role a repo plays comes from the name of the config directory it ships.
The core is byte-identical across both repos, so the config on disk is the only
honest answer to "which side am I?" — and book rules 1-2 already require the
cop and thief configs to be kept strictly apart.
"""

from pathlib import Path

from ..constants import Role
from ..net.inbox import Inboxes
from ..net.mcp_server import PeerServer
from ..net.preflight_checks import standard_checks
from ..net.tunnel import Tunnel
from ..shared.config import ConfigManager
from ..shared.events import EventBus
from .actions import AgentActions
from .sdk import AgentSdk

CONFIG_ROOT = Path("config")


def default_config_path() -> Path:
    """The role directory this repo ships, whichever role that is."""
    for role in (Role.COP, Role.THIEF):
        candidate = CONFIG_ROOT / role.value
        if (candidate / "game.toml").exists():
            return candidate
    return CONFIG_ROOT


def resolve_role(role_dir: Path, override: str = "") -> Role:
    """The role we are playing, from `--role` or the config directory name.

    The directory is the real source: each repo ships exactly one of
    `config/police/` or `config/thief/`, and book rules 1-2 require them kept
    apart. Inventing a `role` key would add a second answer that could disagree
    with the files actually on disk.
    """
    if override:
        return Role(override)
    return Role(role_dir.name)


def build_sdk(
    config: Path | None = None,
    role: str = "",
    dashboard: bool = True,
    workspace: Path | None = None,
) -> AgentSdk:
    """Load configuration and return an SDK wired to real services."""
    role_dir = config or default_config_path()
    manager = ConfigManager.load(role_dir, shared_config=CONFIG_ROOT / "game.json")
    chosen = resolve_role(role_dir, role)
    bus = EventBus(path=(workspace or Path("workspace")) / "events.jsonl")
    server = PeerServer(
        inboxes=Inboxes(emit=bus.publish),
        port=int(manager.get("network.my_port", 8802)),
        emit=bus.publish,
    )
    tunnel = _build_tunnel(manager, chosen, bus)
    actions = AgentActions(
        server=server,
        tunnel=tunnel,
        checks=standard_checks(manager, server, tunnel),
        workspace=workspace or Path("workspace"),
        emit=bus.publish,
    )
    sdk = AgentSdk(events=bus, actions=actions)
    if dashboard:
        _attach_dashboard(sdk, actions, manager, bus)
    return sdk


def _attach_dashboard(
    sdk: AgentSdk, actions: AgentActions, manager: ConfigManager, bus: EventBus
) -> None:
    """Give the SDK a dashboard that reads it, and subscribe it to the bus.

    Imported here rather than at module scope so the SDK stays usable — and
    testable — in an environment without the web stack installed.
    """
    from ..ui.app import ConnectionHub, attach_bus
    from ..ui.server import DashboardServer

    hub = ConnectionHub()
    attach_bus(bus, hub)
    actions.attach_dashboard(DashboardServer(sdk, hub, port=int(manager.get("ui.port", 8000))))


def _build_tunnel(manager: ConfigManager, role: Role, bus: EventBus) -> Tunnel | None:
    """A named tunnel when one is configured; otherwise local-only play."""
    hostname = str(manager.get("tunnel.hostname", ""))
    if not hostname:
        return None
    return Tunnel(
        provider=str(manager.get("tunnel.provider", "cloudflare")),
        hostname=hostname,
        port=int(manager.get("network.my_port", 8802)),
        name=str(manager.get("tunnel.name", role.value)),
        emit=bus.publish,
    )
