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
from typing import Any

from pydantic import BaseModel

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


def shared_config_for(role_dir: Path) -> Path:
    """The signed terms that belong beside this private config.

    `--config <dir>/police` must load `<dir>/game.json`, not the repository's
    default. The shared file used to be read from `config/game.json`
    unconditionally, so pointing the agent at a per-match directory loaded that
    match's private settings alongside *our opening proposal* rather than the
    terms we agreed with that opponent.

    The signature check would have caught it as a refusal to play rather than a
    silently wrong game, but a refusal minutes before a match is still a defect,
    and per-opponent config directories are exactly how the runbook says to
    prepare (`docs/LEAGUE_OPS.md`).
    """
    beside = role_dir.parent / "game.json"
    return beside if beside.exists() else CONFIG_ROOT / "game.json"


def build_sdk(
    config: Path | None = None,
    role: str = "",
    dashboard: bool = True,
    workspace: Path | None = None,
) -> AgentSdk:
    """Load configuration and return an SDK wired to real services."""
    role_dir = config or default_config_path()
    manager = ConfigManager.load(role_dir, shared_config=shared_config_for(role_dir))
    chosen = resolve_role(role_dir, role)
    bus = EventBus(path=(workspace or Path("workspace")) / "events.jsonl")
    inboxes = Inboxes(emit=bus.publish)
    server = PeerServer(
        inboxes=inboxes,
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
        opponent_url=str(manager.get("network.opponent_url", "")),
    )
    sdk = AgentSdk(events=bus, actions=actions)
    if dashboard:
        _attach_dashboard(sdk, actions, manager, bus)
    _attach_match(actions, manager, chosen, bus, inboxes)
    return sdk


def _attach_match(actions: AgentActions, manager: ConfigManager, role: Role, bus, inboxes) -> None:
    """Give the agent the ability to actually play, when it knows an opponent.

    Without an opponent URL there is nothing to play against, and that is a
    normal pre-match state rather than an error — `preflight` is what reports
    it. Import is local so a config-only command never pays for the LLM stack.
    """
    if not str(manager.get("network.opponent_url", "") or "").strip():
        return
    from .match_setup import build_match, build_transport

    transport = build_transport(manager, bus, inboxes)
    actions.attach_match(build_match(
        manager, role, transport, _speaker(manager, bus), bus,
        handshake=_handshake(manager, bus, inboxes, transport),
    ))


def _handshake(manager: ConfigManager, bus, inboxes, transport):
    """The pre-game agreement swap, as a callable the match runs first."""
    from ..negotiation.handshake import exchange_agreement
    from ..negotiation.identity import identity_from_config
    from ..negotiation.terms import terms_from_config

    def run():
        """Sign, swap and verify the terms before any move is played."""
        return exchange_agreement(
            terms=terms_from_config(manager),
            identity=identity_from_config(manager),
            send=lambda payload: transport.send_negotiate(payload),
            # The inbox hands back a validated pydantic model; the handshake and
            # the contract both work in plain dicts, and `verify_peer` indexes
            # the message directly.
            receive=lambda timeout: _as_dict(inboxes.poll("negotiate", timeout=timeout)),
            timeout=float(manager.get("network.handshake_timeout_seconds", 60)),
            emit=bus.publish,
        )

    return run


def _as_dict(message: Any) -> dict[str, Any] | None:
    """A polled inbox message as a plain dict, or None when nothing arrived.

    The inbox hands back a validated pydantic model; `Contract.verify_peer`
    and the handshake both index a plain mapping.
    """
    if message is None:
        return None
    if isinstance(message, BaseModel):
        return message.model_dump()
    if isinstance(message, dict):
        return message
    return None


def _speaker(manager: ConfigManager, bus) -> Any:
    """The hint writer: real providers when configured, templates otherwise."""
    from ..llm.router import LLMRouter
    from ..llm.speaker import Speaker
    from ..llm.template_provider import TemplateProvider

    template = TemplateProvider(map_area=str(manager.get("world.map_area", "")))
    return Speaker(
        router=LLMRouter(providers=[template], emit=bus.publish),
        template=template,
        arena=str(manager.get("world.map_area", "")),
        hint_max_words=int(manager.get("world.hint_max_words", 15)),
        every_n_steps=int(manager.get("llm.every_n_steps", 1)),
        emit=bus.publish,
    )


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
