"""Assembling a playable match from configuration.

Kept apart from `bootstrap` because it is the heaviest wiring in the project
and has one job: turn a config file and an opponent URL into a `MatchRunner`
that can actually play. Until this existed the agent could serve an opponent
and never make a move — every part was built and tested, and nothing joined
them at the production edge.
"""

import time
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from ..constants import Role
from ..domain.game_state import GameState
from ..domain.match import MatchRunner
from ..domain.params import GameParams
from ..domain.scoring import ScoreTable
from ..domain.series import SeriesTracker
from ..llm.speaker import Speaker
from ..net.deadline import DeadlineTracker
from ..net.mcp_client import PeerClient
from ..net.peer_transport import PeerTransport
from ..shared.events import EventBus
from ..shared.gatekeeper import ApiGatekeeper
from ..shared.rate_limits import for_service, load_rate_limits
from ..strategy.cop_brain import CopBrain
from ..strategy.thief_brain import ThiefBrain
from .plugins import resolve
from .state_setup import state_factory


def _accepts(brain: Any, field: str) -> bool:
    """Whether this brain declares `field`, so we never pass one it lacks."""
    return is_dataclass(brain) and any(each.name == field for each in fields(brain))  # type: ignore[arg-type]


def brain_factory(manager: Any = None) -> Any:
    """The policy for each role, honouring a brain named in configuration.

    `strategy.cop_class` / `strategy.thief_class` accept a
    `"module:Attribute"` path (see `docs/EXTENDING.md`); unset means the brains
    that ship. Resolution happens **here, once, at wiring time** rather than per
    turn, so a bad path fails while starting up instead of mid-match.

    `board_supplier` rather than a captured board: barriers appear mid-game, and
    a brain reasoning over a stale board walks into walls it declared.
    """
    cop = resolve(manager.get("strategy.cop_class") if manager else None, CopBrain)
    thief = resolve(manager.get("strategy.thief_class") if manager else None, ThiefBrain)
    tuning = {
        Role.COP: _tuning(manager, "cop", cop),
        Role.THIEF: _tuning(manager, "thief", thief),
    }
    # `strength.level` lives in its own config section, and `_tuning` only ever
    # read `[strategy.<side>]` — so `ThiefBrain.strength` kept its dataclass
    # default `"full"` no matter what `match_day.py warmup` wrote. Every
    # "sandbagged" warm-up this project has played was played at full strength,
    # and the switch that exists to *stop* us showing our real policy to a team
    # we may meet again did nothing at all.
    #
    # Passed only to brains that declare the field, so a replacement brain
    # loaded through `strategy.thief_class` is not handed an argument it never
    # asked for — the same rule `_tuning` applies to every other dial.
    level = str(manager.get("strength.level", "full")) if manager else "full"
    for role, brain in ((Role.COP, cop), (Role.THIEF, thief)):
        if _accepts(brain, "strength"):
            tuning[role]["strength"] = level

    def build(role: Role, state: GameState) -> Any:
        """Instantiate the brain for one mini-game."""
        supplier = lambda: state.board  # noqa: E731 - a one-line accessor is clearer inline
        return (cop if role is Role.COP else thief)(board_supplier=supplier, **tuning[role])

    return build


def _tuning(manager: Any, side: str, brain: Any) -> dict[str, Any]:
    """The configured dials for one brain, checked against what it accepts.

    Only declared keys are passed, so an unset dial keeps the brain's own
    default rather than being overwritten with `None`. A key the brain does not
    have raises **here, while wiring**, naming both the key and the dials that
    do exist.

    That last part is not defensiveness for its own sake. TOML assigns a bare
    key to the most recent table header, so writing `cop_class` after
    `[strategy.thief]` quietly makes it a *thief* tunable — which handed
    `ThiefBrain` a `cop_class` argument and killed a live match at the first
    mini-game. A config mistake should stop the agent at startup, not mid-game.
    """
    if manager is None:
        return {}
    section = {
        key: value
        for key, value in dict(manager.get(f"strategy.{side}", {}) or {}).items()
        if not key.startswith("_")
    }
    accepted = {field.name for field in fields(brain)} if is_dataclass(brain) else set()  # type: ignore[arg-type]
    unknown = sorted(set(section) - accepted) if accepted else []
    if unknown:
        raise ValueError(
            f"config [strategy.{side}] names {unknown}, which "
            f"{getattr(brain, '__name__', brain)} does not accept; "
            f"its tunables are {sorted(accepted - {'board_supplier'})}"
        )
    return section


#: The default factory, for callers with no configuration to consult.
build_brain = brain_factory()


def build_transport(manager: Any, bus: EventBus, inboxes: Any) -> PeerTransport:
    """The live link to the opponent, rate-limited and deadline-bounded.

    The resolver cache is installed here, before the first call, because DNS is
    what actually cost us mini-games: three against uoh-sqak died to
    `Temporary failure in name resolution` on a mid-game reconnect, on a machine
    whose lookups measure 502 ms median and 1.9 s worst case. An opponent's
    address does not move inside a match, so asking twice buys nothing.
    """
    from ..net import dns_cache

    opponent = str(manager.require("network.opponent_url"))
    dns_cache.install()
    dns_cache.warm(opponent, emit=bus.publish)
    limits = load_rate_limits(Path(str(manager.get("paths.rate_limits", "config/rate_limits.json"))))
    response_timeout = float(manager.get("network.response_timeout_seconds", 30))
    call_timeout = float(manager.get("network.call_timeout_seconds", 10))
    # A per-call cap equal to the signed deadline is not a cap at all. One
    # delivered-but-unanswered push, one backoff sleep and a retry is already
    # past 30 s, so we can breach a deadline we signed while every individual
    # call looks healthy in the log. imreeyal lost two sub-games to exactly
    # this and wrote up the arithmetic; the cap has to be strictly under the
    # deadline for the retry to fit inside it at all.
    if call_timeout >= response_timeout:
        raise ValueError(
            f"network.call_timeout_seconds={call_timeout} must be strictly under "
            f"network.response_timeout_seconds={response_timeout}: a per-call cap at or "
            "above the signed deadline lets one retry breach terms we agreed to"
        )
    client = PeerClient(
        opponent_url=opponent,
        call_timeout=call_timeout,
        # `mcp_peer`, the name the config actually declares. Asking for "peer"
        # fell through to `default` — 30 requests a minute, one message every
        # two seconds — and the opponent is not a quota-limited third-party
        # API. Throttling our own protocol traffic protects nobody and risks
        # pushing a reply past their 30-second deadline, forfeiting a game to
        # our own limiter.
        gatekeeper=ApiGatekeeper(
            service="mcp_peer", config=for_service(limits, "mcp_peer"), emit=bus.publish
        ),
        emit=bus.publish,
    )
    deadlines = DeadlineTracker(
        response_timeout=response_timeout,
        max_retries=int(manager.get("network.max_retries", 3)),
        emit=bus.publish,
    )
    return PeerTransport(inboxes=inboxes, client=client, deadlines=deadlines, emit=bus.publish)


def _our_endpoint(manager: Any) -> str:
    """The public address peers reach us on, from the declared tunnel hostname.

    Empty when no tunnel is configured, which `fault_attribution` reads as "we
    cannot demonstrate our own health" and answers `indeterminate` — the right
    answer, since a local-only run has nothing to compare against.
    """
    hostname = str(manager.get("tunnel.hostname", "") or "").strip()
    return f"https://{hostname}/mcp" if hostname else ""


def build_match(
    manager: Any,
    role: Role,
    transport: Any,
    speaker: Speaker | Any,
    bus: EventBus,
    scoring: dict[str, Any] | None = None,
    handshake: Any = None,
    meter: Any = None,
    observer: Any = None,
) -> MatchRunner:
    """A runner ready to play the agreed series against one opponent."""
    params = GameParams.from_config(manager.as_dict())
    table = ScoreTable.from_config({"scoring": scoring or manager.section("scoring")})
    tracker = SeriesTracker(
        our_group=str(manager.get("game.group_id", "us")),
        their_group=str(manager.get("network.opponent_group_id", "them")),
        table=table,
        first_role=role,
        total_games=int(manager.get("network_and_league.num_games", 6)),
    )
    return MatchRunner(
        params=params,
        tracker=tracker,
        transport=transport,
        build_state=state_factory(manager, meter, bus.publish),
        build_brain=brain_factory(manager),
        speaker=speaker,
        clock=time.monotonic,
        first_role=role,
        emit=bus.publish,
        handshake=handshake,
        # Our endpoint and theirs, so a connection failure can be attributed to
        # a side while it is still failing rather than argued about later.
        # Built from `tunnel.hostname` because that is the declared key; there
        # is no `network.public_url` — `AgentActions.public_url` is a derived
        # property, and reading it as config was a key nobody declares. Caught
        # by `test_no_hardcoded_tunables`, which is exactly its job.
        urls=(_our_endpoint(manager), str(manager.get("network.opponent_url", "") or "")),
        # T-2447: a failed agreement retries the SAME sub-game this many times
        # before it resolves as a technical outcome. Config, not code — like
        # every other limit here.
        handshake_retries=int(manager.get("network.handshake_retries", 2)),
        meter=meter,
        observer=observer,
        response_timeout=float(manager.get("network.response_timeout_seconds", 30)),
        max_retries=int(manager.get("network.max_retries", 3)),
        # Spent only after a mini-game we abandoned, so the peer has closed its
        # side before we offer it the next handshake (docs: domain/settle.py).
        watchdog_seconds=float(manager.get("network.watchdog_threshold_seconds", 60)),
    )
