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

from ..constants import EndReason, Phase, Role
from ..shared.events import Emit
from .fsm import GameStateMachine
from .game_state import GameState
from .handshake_retry import agree_on_terms
from .match_audit import audit_or_skip
from .match_record import now_iso, played_record
from .match_resolution import resolve_abandoned, resolve_unplayed, tokens_for
from .orchestrator import Orchestrator
from .params import GameParams
from .series import SeriesResult, SeriesTracker, role_for
from .turn_loop import run_turn_loop

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
        # The mini-game currently in play, so a crash can still report how far
        # it got. None until the first one starts.
        self._live_state: GameState | None = None
        self.games: list[dict[str, Any]] = []

    def play_series(self) -> SeriesResult:
        """Play every remaining mini-game and return the series result.

        Two different failures, two different resolutions, and the series
        survives both.

        The handshake runs here, not inside the sub-game, because its failure
        must not consume a number. We used to advance the counter on a failed
        sub-game while the opponent retried the same one — after two failures
        we were numbering games 3 and 4 against their 5 and 6, and two reports
        describing one match with different `sub_game_number`s are contradictory
        (rules 33-35 can void both teams). A failed agreement now retries the
        *same* sub-game, bounded; only exhaustion resolves it as a technical
        outcome.

        A mini-game that agreed and then blew up is a separate case: most
        plausibly the `RuntimeError` the gatekeeper raises once a send has
        exhausted its retries. That used to propagate through `play_match` to
        the CLI and kill the process — in a real match three failed
        `receive_turn` calls ended it at sub-game 3, so 4, 5 and 6 were never
        played and our endpoint went dark. The opponent met the same blip with
        a watchdog, scored the game, and carried on. It is now scored a
        `TIMEOUT`, the verdict their watchdog reaches, so both sides describe
        the game the same way. `match_resolution` holds both shapes.
        """
        while not self.tracker.is_complete:
            sub_game = self.tracker.next_sub_game
            role = role_for(sub_game, self.first_role)
            if not agree_on_terms(
                self._handshake, sub_game, self._handshake_retries, self._emit
            ):
                self.games.append(
                    resolve_unplayed(self.tracker, sub_game, role, EndReason.OPPONENT_QUIT)
                )
                continue
            try:
                self.play_sub_game(sub_game, role)
            except Exception as error:  # noqa: BLE001 - scored, never fatal to the series
                steps = getattr(self._live_state, "step", 0)
                self._emit({
                    "event": "subgame.abandoned", "sub_game": sub_game, "steps": steps,
                    "role": role.value, "error": f"{type(error).__name__}: {error}",
                })
                self.games.append(resolve_abandoned(self.tracker, sub_game, role, steps))
            finally:
                # Whatever happened, we are between mini-games now, so the
                # opponent's next handshake must be welcome again.
                self._transport.finish_sub_game()
        result = self.tracker.result()
        self._emit({"event": "series.complete", "sub_games": len(self.tracker.outcomes)})
        return result

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
        # Held so an abandoned game can report the steps it actually played;
        # filing those as zero is what made our ledger contradict theirs.
        self._live_state = state
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

        reason = run_turn_loop(orchestrator, self.params.max_moves) or EndReason.SURVIVAL
        report = audit_or_skip(state, reason, self._transport, self._audit_timeout, self._emit)
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
            sub_game, started_at, outcome, state, report, tokens_for(self._meter, sub_game)
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

    def _new_orchestrator(self, state: GameState, fsm: GameStateMachine, role: Role) -> Orchestrator:
        """One conductor per mini-game, with a brain chosen for the role."""
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
