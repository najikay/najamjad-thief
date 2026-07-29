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
from ..domain.belief import BeliefGrid
from ..domain.board import Board
from ..domain.game_state import GameState
from ..domain.ledger import CommitLedger
from ..domain.match import MatchRunner
from ..domain.params import GameParams
from ..domain.scent import ScentField
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


def build_state(params: GameParams, role: Role, sub_game: int) -> GameState:
    """A fresh mini-game state; nothing may leak between sub-games."""
    board = Board(params)
    start = params.cop_start if role is Role.COP else params.thief_start
    return GameState(
        board=board,
        role=role,
        sub_game=sub_game,
        own_position=start,
        belief=BeliefGrid(board),
        own_scent=ScentField(board_size=board.size),
        opponent_scent=ScentField(board_size=board.size),
        ledger=CommitLedger(sub_game=sub_game),
    )


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
    """The live link to the opponent, rate-limited and deadline-bounded."""
    limits = load_rate_limits(Path(str(manager.get("paths.rate_limits", "config/rate_limits.json"))))
    client = PeerClient(
        opponent_url=str(manager.require("network.opponent_url")),
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
        response_timeout=float(manager.get("network.response_timeout_seconds", 30)),
        max_retries=int(manager.get("network.max_retries", 3)),
        emit=bus.publish,
    )
    return PeerTransport(inboxes=inboxes, client=client, deadlines=deadlines, emit=bus.publish)


def build_match(
    manager: Any,
    role: Role,
    transport: Any,
    speaker: Speaker | Any,
    bus: EventBus,
    scoring: dict[str, Any] | None = None,
    handshake: Any = None,
    meter: Any = None,
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
        build_state=build_state,
        build_brain=brain_factory(manager),
        speaker=speaker,
        clock=time.monotonic,
        first_role=role,
        emit=bus.publish,
        handshake=handshake,
        meter=meter,
        response_timeout=float(manager.get("network.response_timeout_seconds", 30)),
        max_retries=int(manager.get("network.max_retries", 3)),
    )
