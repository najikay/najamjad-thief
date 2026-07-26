"""Assembling a playable match from configuration.

Kept apart from `bootstrap` because it is the heaviest wiring in the project
and has one job: turn a config file and an opponent URL into a `MatchRunner`
that can actually play. Until this existed the agent could serve an opponent
and never make a move — every part was built and tested, and nothing joined
them at the production edge.
"""

import time
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


def build_brain(role: Role, state: GameState) -> Any:
    """The policy for this role, reading the board as it changes.

    `board_supplier` rather than a captured board: barriers appear mid-game,
    and a brain reasoning over a stale board walks into walls it declared.
    """
    supplier = lambda: state.board  # noqa: E731 - a one-line accessor is clearer inline
    return CopBrain(board_supplier=supplier) if role is Role.COP else ThiefBrain(
        board_supplier=supplier
    )


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
        build_brain=build_brain,
        speaker=speaker,
        clock=time.monotonic,
        first_role=role,
        emit=bus.publish,
        response_timeout=float(manager.get("network.response_timeout_seconds", 30)),
        max_retries=int(manager.get("network.max_retries", 3)),
    )
