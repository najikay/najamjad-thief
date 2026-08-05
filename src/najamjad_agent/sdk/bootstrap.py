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

from ..constants import Role
from ..negotiation.flow import Negotiation
from ..net.inbox import Inboxes
from ..net.mcp_server import PeerServer
from ..net.preflight_checks import standard_checks
from ..net.tunnel import Tunnel
from ..shared.app_config import load_setup, setting
from ..shared.config import ConfigManager
from ..shared.environment import load_env
from ..shared.events import EventBus
from ..shared.logging_setup import setup_logging
from .actions import AgentActions

# Cheap at import time: every vendor import inside it is deferred.
from .handshake_setup import _handshake, _inbound_ceiling
from .llm_setup import build_speaker, token_meter
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


def _guard_counted_strength(manager: ConfigManager) -> None:
    """Refuse to build an agent for a counted match at less than full strength.

    `shared/strength.guard_counted` was written, documented, tested and then
    **never called from anywhere**, so the refusal it exists to perform did not
    happen. Meanwhile `scripts/match_day.py warmup` writes `level =
    "sandbagged"` into a file nothing reads — the agent played full strength
    regardless, and the guard that was supposed to catch the reverse mistake,
    arming a warm-up and forgetting to re-arm before the counted series, never
    ran once.

    Here rather than in the CLI because this is where the config is loaded, so
    every entry point that builds an agent is covered rather than the one
    command someone remembered to edit. A counted match cannot be replayed.
    """
    from ..shared.practice import current
    from ..shared.strength import guard_counted

    guard_counted(manager.get("strength.level", "full"), counted=not current().enabled)


def build_sdk(
    config: Path | None = None,
    role: str = "",
    dashboard: bool = True,
    workspace: Path | None = None,
    opponent: str | None = None,
    group_id: str | None = None,
) -> AgentSdk:
    """Load configuration and return an SDK wired to real services."""
    # Before anything reads a credential. `.env` was documented, git-ignored and
    # referenced by the README, and nothing ever loaded it — so a key pasted
    # there had precisely the effect of no key at all, silently, because an
    # uncredentialed vendor is skipped rather than reported broken.
    load_env()
    role_dir = config or default_config_path()
    # Diagnostics first: everything after this point is entitled to a logger,
    # and a failure here is reported rather than raised (guidelines §7.2).
    setup = load_setup()
    setup_logging(
        path=setting(setup, "paths.logging", "config/logging_config.json"),
        workspace=workspace or Path(setting(setup, "paths.workspace", "workspace")),
    )
    manager = ConfigManager.load(role_dir, shared_config=shared_config_for(role_dir))
    _guard_counted_strength(manager)
    if group_id:
        # A practice-only identity, applied at runtime so it never touches the
        # committed config. Two agents from one team both declaring "najamjad"
        # collapse every per-group dict in the report to a single key — two
        # scores, one entry, silently. The alternative was editing the shipped
        # config and loosening the test that pins our real identity, which
        # would let a wrong group_id ship at submission.
        manager.overlay({"game": {"group_id": group_id}})
    if opponent:
        # Late and narrow: only `network.opponent_*`, so a card can never
        # reach a signed game term (see shared/opponents.py).
        from ..shared.opponents import as_overlay, load_opponent

        card = load_opponent(opponent)
        manager.overlay(as_overlay(card))
    chosen = resolve_role(role_dir, role)
    bus = EventBus(path=(workspace or Path(setting(setup, "paths.workspace", "workspace")))
                   / "events.jsonl")
    inboxes = Inboxes(emit=bus.publish, max_per_minute=_inbound_ceiling(manager))
    server = PeerServer(
        inboxes=inboxes,
        port=int(manager.get("network.my_port", 8802)),
        emit=bus.publish,
    )
    tunnel = _build_tunnel(manager, chosen, bus)
    # One negotiation object, shared by the half that *acts* on it
    # (`AgentActions.approve_terms`) and the half that *renders* it
    # (`AgentSdk.negotiation_timeline`). They are separate attributes on
    # separate classes, and wiring only the first left the dashboard's timeline
    # permanently empty while `flow.py`'s own docstring promised it was
    # rendered.
    talks = Negotiation(
        our_group=str(manager.get("game.group_id", "najamjad")), emit=bus.publish
    )
    actions = AgentActions(
        server=server,
        tunnel=tunnel,
        checks=standard_checks(manager, server, tunnel),
        workspace=workspace or Path(setting(setup, "paths.workspace", "workspace")),
        emit=bus.publish,
        opponent_url=str(manager.get("network.opponent_url", "")),
        wait_seconds=float(manager.get("network.opponent_wait_seconds", 900)),
        # Without this `_negotiation` is None and both dashboard negotiation
        # controls raise `AttributeError` on click — the buttons were wired to
        # nothing.
        #
        # It does **not** make the playbook's red lines reachable, and an
        # earlier version of this comment claimed it did. `Playbook.evaluate`
        # runs only from `Negotiation.receive`, which handles an *incoming*
        # proposal, and nothing routes to it: the UI exposes an approve
        # endpoint and no receive endpoint, and a real match is agreed
        # take-it-or-leave-it by `exchange_agreement`. So the ceilings are
        # enforced in `evaluate` and exercised by tests, and a peer's proposal
        # still cannot reach them in production. Filed rather than papered
        # over.
        negotiation=talks,
    )
    # One meter for the whole process: the dashboard's budget panel and the
    # token figures in the emailed report must be the same numbers, not two
    # counts that can disagree about whether we are near the agreed cap.
    meter = token_meter(manager, bus)
    sdk = AgentSdk(events=bus, actions=actions, meter=meter, negotiation=talks,
                   controls_enabled=bool(setting(setup, "features.controls", False)))
    if dashboard:
        _attach_dashboard(sdk, actions, manager, bus)
    _attach_match(actions, manager, chosen, bus, inboxes, meter, sdk)
    return sdk


def _attach_match(
    actions: AgentActions,
    manager: ConfigManager,
    role: Role,
    bus,
    inboxes,
    meter: Any = None,
    observer: Any = None,
) -> None:
    """Give the agent the ability to actually play, when it knows an opponent.

    Without an opponent URL there is nothing to play against, and that is a
    normal pre-match state rather than an error — `preflight` is what reports
    it. Import is local so a config-only command never pays for the LLM stack.
    """
    if not str(manager.get("network.opponent_url", "") or "").strip():
        return
    from .match_setup import build_match, build_transport

    transport = build_transport(manager, bus, inboxes)
    speaker = build_speaker(manager, bus, meter, observer)
    if observer is not None:
        # So the provider badge can name whoever actually answered.
        observer.attach_router(speaker._router)
    # Before the series, so the vendor's cold start is paid here and not inside
    # game 1's turn deadline. Measured: a cold DeepSeek call takes 27-61 s
    # against a 30 s turn budget, and game 1 of a real match took 153 s while
    # games 2-6 took ~15 s. A timeout cannot fix it — those calls succeed,
    # just slowly — so the cost has to move, not be bounded.
    from ..llm.warm_up import warm_up

    warm_up(speaker._router, emit=bus.publish)
    # One dict shared by the handshake and the filer: the handshake learns the
    # opponent's identity and the locked contract hash, and the artifacts cannot
    # be written without both.
    session: dict[str, Any] = {}
    actions.attach_match(build_match(
        manager, role, transport, speaker, bus,
        handshake=_handshake(manager, bus, inboxes, transport, session),
        meter=meter,
        observer=observer,
    ))
    from .match_filing import build_filer

    actions.attach_filer(build_filer(manager, bus, session, actions, load_setup(), observer))


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
    port = int(setting(load_setup(), "ui.port", 8000))
    actions.attach_dashboard(DashboardServer(sdk, hub, port=port))


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
