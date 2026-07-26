"""Driving a whole match: six mini-games, alternating roles, audited each time.

This is the spine the rest of the agent hangs from. Every piece it uses already
existed — the orchestrator conducts one mini-game, `SeriesTracker` scores a
series, `PeerTransport` reaches the peer — but nothing joined them, so the agent
could answer a peer and never actually play one.

The runner owns no rules. It decides when to start a mini-game, whose turn
order applies, and when the series is over; captures, survival and scoring are
all decided elsewhere and merely recorded here.
"""

from collections.abc import Callable
from typing import Any

from ..constants import EndReason, Role
from ..shared.events import Emit
from .audit import SKIP_AUDIT_REASONS, AuditReport
from .fsm import GameStateMachine
from .game_state import GameState
from .match_audit import exchange_audit
from .orchestrator import Orchestrator
from .params import GameParams
from .series import SeriesResult, SeriesTracker, role_for

StateFactory = Callable[[GameParams, Role, int], GameState]
# The brain factory receives the state as well as the role, because a brain
# reasons over the *current* board — barriers appear mid-game — and gets it from
# a `board_supplier`, not from `TurnFacts`. Handing over only the role left the
# caller no way to wire that, and every real brain raised `AttributeError` the
# first time it was asked to move.
BrainFactory = Callable[[Role, GameState], Any]


class MatchRunner:
    """Plays a full series against one opponent."""

    def __init__(
        self,
        params: GameParams,
        tracker: SeriesTracker,
        transport: Any,
        build_state: StateFactory,
        build_brain: BrainFactory,
        speaker: Any,
        clock: Any,
        first_role: Role = Role.COP,
        emit: Emit | None = None,
        audit_timeout: float = 30.0,
        response_timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Wire the runner; everything it needs is injected, nothing imported.

        Timeouts are separate arguments rather than fields of `GameParams`:
        those are the *agreed game rules*, and how long we personally wait for a
        packet is ours to choose and not something the opponent signed up to.
        """
        self._response_timeout = response_timeout
        self._max_retries = max_retries
        self.params = params
        self.tracker = tracker
        self.first_role = first_role
        self._transport = transport
        self._build_state = build_state
        self._build_brain = build_brain
        self._speaker = speaker
        self._clock = clock
        self._emit = emit or (lambda _event: None)
        self._audit_timeout = audit_timeout
        self.games: list[dict[str, Any]] = []

    def play_series(self) -> SeriesResult:
        """Play every remaining mini-game and return the series result."""
        while not self.tracker.is_complete:
            sub_game = self.tracker.next_sub_game
            self.play_sub_game(sub_game, role_for(sub_game, self.first_role))
        result = self.tracker.result()
        self._emit({"event": "series.complete", "sub_games": len(self.tracker.outcomes)})
        return result

    def play_sub_game(self, sub_game: int, role: Role) -> dict[str, Any]:
        """Play one mini-game to its end, audit it, and record the outcome."""
        state = self._build_state(self.params, role, sub_game)
        fsm = GameStateMachine(game_uid=f"g{sub_game:02d}")
        orchestrator = self._new_orchestrator(state, fsm, role)
        self._emit({"event": "subgame.started", "sub_game": sub_game, "role": role.value})

        reason = self._turn_loop(orchestrator) or EndReason.SURVIVAL
        report = self._audit(state, reason)
        outcome = self.tracker.record(
            end_reason=reason,
            role=role,
            steps=state.step,
            # A skipped audit is not a failed one. Treating it as failure
            # rewrote a plain timeout into `tamper_forfeit` — accusing an
            # opponent of forgery for going offline, and mislabelling our own
            # result in the report we file.
            audit_passed=report.passed or report.skipped,
        )
        record = {
            "sub_game": sub_game,
            "role": role.value,
            "end_reason": outcome.end_reason.value,
            "steps": state.step,
            "audit": report.banner,
            # Only after an audit actually happened. With no audit the nonces
            # were never released, and the ledger rightly refuses to hand them
            # over (rule 18) — a game that ended in a timeout has nothing to
            # reveal, and asking anyway raised into the match loop.
            "records": [] if report.skipped else state.ledger.audit_payload(),
        }
        self.games.append(record)
        self._emit({"event": "subgame.finished", **{k: v for k, v in record.items() if k != "records"}})
        return record

    def _audit(self, state: GameState, reason: EndReason) -> AuditReport:
        """Exchange reveals — unless the protocol never reached a clean close.

        `domain.audit` already declares which endings have nothing to audit: a
        timeout, a stop, an opponent quitting. Demanding a reveal there means
        holding a peer to a step they never got to, and reading their silence
        as forgery.
        """
        if reason in SKIP_AUDIT_REASONS:
            self._emit({"event": "audit.skipped", "reason": reason.value})
            return AuditReport(passed=False, skipped=True)
        return exchange_audit(state.ledger, self._transport, self._audit_timeout)


    def _new_orchestrator(self, state: GameState, fsm: GameStateMachine, role: Role) -> Orchestrator:
        """One conductor per mini-game, with a brain chosen for the role."""
        from ..constants import Phase

        fsm.to(Phase.WAITING_FOR_OPPONENT)
        return Orchestrator(
            state=state,
            fsm=fsm,
            transport=self._transport,
            brain=self._build_brain(role, state),
            speaker=self._speaker,
            clock=self._clock,
            emit=self._emit,
            response_timeout=self._response_timeout,
            max_retries=self._max_retries,
        )

    def _turn_loop(self, orchestrator: Orchestrator) -> EndReason | None:
        """Alternate with the peer until someone's move ends the mini-game.

        The bound is `max_moves` full turns, not a `while True`: a peer that
        answers forever must not be able to keep us in a game the rules say has
        already been decided on survival.
        """
        for _ in range(self.params.max_moves + 1):
            first, second = (
                (orchestrator.take_turn, orchestrator.receive_turn)
                if orchestrator.moves_first
                else (orchestrator.receive_turn, orchestrator.take_turn)
            )
            for act in (first, second):
                ended = act()
                if ended is not None:
                    return ended
        return None
