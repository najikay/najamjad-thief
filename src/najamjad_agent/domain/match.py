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
from .audit import AuditReport
from .fsm import GameStateMachine
from .game_state import GameState
from .match_audit import audit_or_skip
from .match_record import now_iso, played_record, unplayed_record
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
        handshake: Callable[[], Any] | None = None,
        handshake_retries: int = 2,
        meter: Any = None,
        observer: Any = None,
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
        self._handshake = handshake
        self._handshake_retries = handshake_retries
        self._meter = meter
        self._observer = observer
        self.games: list[dict[str, Any]] = []

    def play_series(self) -> SeriesResult:
        """Play every remaining mini-game and return the series result.

        The handshake runs here, not inside the sub-game, because its failure
        must not consume a number. We used to advance the counter on a failed
        sub-game while the opponent retried the same one — after two failures
        we were numbering games 3 and 4 against their 5 and 6, and two reports
        describing one match with different `sub_game_number`s are contradictory
        (rules 33-35 can void both teams). A failed agreement now retries the
        *same* sub-game, bounded; only exhaustion resolves it, as a technical
        outcome, so a dead peer costs one mini-game and never the series.
        """
        while not self.tracker.is_complete:
            sub_game = self.tracker.next_sub_game
            role = role_for(sub_game, self.first_role)
            if not self._agree(sub_game):
                self._record_unplayed(sub_game, role)
                continue
            self.play_sub_game(sub_game, role)
        result = self.tracker.result()
        self._emit({"event": "series.complete", "sub_games": len(self.tracker.outcomes)})
        return result

    def _agree(self, sub_game: int) -> bool:
        """Run the pre-game handshake, retrying the same sub-game on failure.

        Catches broadly because the handshake is an injected boundary — the
        domain must not import the negotiation layer to name its exception, and
        any failure here means the same thing: no agreed terms, nothing to play
        yet. Every attempt is announced; a silent retry hides the tunnel
        problem the operator needs to hear about before it happens mid-series.
        """
        if self._handshake is None:
            return True
        for attempt in range(1 + self._handshake_retries):
            try:
                self._handshake()
            except Exception as error:  # noqa: BLE001 - injected boundary, reported
                self._emit({
                    "event": "handshake.retry" if attempt < self._handshake_retries
                    else "handshake.exhausted",
                    "sub_game": sub_game,
                    "attempt": attempt + 1,
                    "error": f"{type(error).__name__}: {error}",
                })
            else:
                return True
        return False

    def _record_unplayed(self, sub_game: int, role: Role) -> None:
        """Resolve a sub-game whose handshake died: one technical loss, 0-0.

        `OPPONENT_QUIT` is already in `SKIP_AUDIT_REASONS` — a peer that never
        agreed to play has nothing to reveal, and demanding an audit would read
        their absence as forgery.
        """
        outcome = self.tracker.record(
            end_reason=EndReason.OPPONENT_QUIT, role=role, steps=0, audit_passed=True
        )
        self.games.append(unplayed_record(sub_game, now_iso(), outcome))

    def play_sub_game(self, sub_game: int, role: Role) -> dict[str, Any]:
        """Play one mini-game to its end, audit it, and record the outcome.

        The transport is reset first: each mini-game restarts step numbering at
        1, and anything the transport remembers about the last game — its step
        high-water mark, or a message that arrived after it ended — makes the
        next one unplayable.
        """
        self._transport.reset()
        started_at = now_iso()
        state = self._build_state(self.params, role, sub_game)
        fsm = GameStateMachine(game_uid=f"g{sub_game:02d}")
        # Hand the live game to whoever is watching — the dashboard reads its
        # board, belief and turn banner off this. `attach_game` existed from
        # the start and nothing ever called it, so every panel that needs a
        # game sat on "Waiting for a game to start…" through six real
        # mini-games while the match played out behind it.
        if self._observer is not None:
            self._observer.attach_game(state, fsm)
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
        record = played_record(
            sub_game, started_at, outcome, state, report, self._tokens_for(sub_game)
        )
        self.games.append(record)
        if report.disputed:
            self._emit({
                "event": "result.disputed",
                "sub_game": sub_game,
                "ours": outcome.end_reason.value,
                "theirs": report.their_claim,
            })
        self._emit({"event": "subgame.finished", **{k: v for k, v in record.items() if k != "records"}})
        return record

    def _tokens_for(self, sub_game: int) -> int:
        """Tokens spent on this mini-game, or 0 when nothing is metering.

        Read off the meter rather than counted here: the meter is what the
        router already writes to and what the budget panel reads, so the report
        cannot disagree with the dashboard about how close to the cap we are.
        """
        meter = self._meter
        if meter is None:
            return 0
        return int(getattr(meter, "per_sub_game", {}).get(sub_game, 0))

    def _audit(self, state: GameState, reason: EndReason) -> AuditReport:
        """Exchange reveals — unless the protocol never reached a clean close."""
        return audit_or_skip(
            state, reason, self._transport, self._audit_timeout, self._emit
        )

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
