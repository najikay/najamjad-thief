"""The Orchestrator — single gateway conducting one mini-game (book rule 3).

Peripheral modules never call each other: the belief engine does not know about
the transport, the strategy does not know about crypto, and the transport knows
nothing about the rules. Everything meets here. That is what makes the whole
turn loop testable against fakes — no network, no LLM, no real clock — which is
precisely the seam Assignment 6 could never exercise.

Ingress handling lives in `turn_ingress` (untrusted input, its own threat
model); this module owns the outgoing half and the end-of-game decision.
"""

from collections.abc import Callable
from typing import Any

from ..constants import EndReason, Move, Phase, Role
from .capture import evaluate_barrier_capture, evaluate_capture, resolve_survival
from .crypto import step_payload
from .fsm import GameStateMachine
from .game_state import GameState, TurnFacts
from .movement import apply_move, legal_moves, place_barrier
from .params import Position
from .ports import Brain, Clock, Speaker, Transport
from .turn_ingress import absorb_turn, decay_after_full_turn, outgoing_extras

THIEF_MOVES_FIRST = True


class Orchestrator:
    """Conducts one mini-game end to end for a single peer."""

    def __init__(
        self,
        state: GameState,
        fsm: GameStateMachine,
        transport: Transport,
        brain: Brain,
        speaker: Speaker,
        clock: Clock,
        emit: Callable[[dict], None] | None = None,
        response_timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Wire the conductor to its subsystems (all injected, none imported)."""
        self.state = state
        self.fsm = fsm
        self._transport = transport
        self._brain = brain
        self._speaker = speaker
        self._clock = clock
        self._emit = emit or (lambda _event: None)
        self._timeout = response_timeout
        self._max_retries = max_retries
        self.end_reason: EndReason | None = None

    @property
    def moves_first(self) -> bool:
        """Thief opens the mini-game (reference-compatible turn order)."""
        return (self.state.role is Role.THIEF) == THIEF_MOVES_FIRST

    def event(self, name: str, **fields: Any) -> None:
        """Publish a correlated event for logs, dashboard and analysis."""
        self._emit({"event": name, "step": self.state.step, **fields})

    def take_turn(self) -> EndReason | None:
        """Compute, seal and send one move; returns an EndReason if we ended it."""
        self.fsm.to(Phase.COMPUTING_MOVE, step=self.state.step + 1)
        self.state.step += 1
        legal = legal_moves(self.state.board, self.state.own_position)
        facts = self.state.facts(legal)
        barrier = self._barrier_choice(facts)
        move = Move.STAY if barrier else self._legal_move(facts, legal)
        hint, intent = self._speaker.compose(facts)
        self._apply_own_action(move, barrier)
        payload = step_payload(
            step=self.state.step,
            role=self.state.role.value,
            sub_game=self.state.sub_game,
            position=self.state.own_position,
            move=f"MOVE:{move.value}",
            intent=intent,
            hint=hint,
            state=self.state.state_string(),
            extra=outgoing_extras(self.state, barrier, self._capture_claim()),
        )
        self._commit_and_send(payload)
        return self._own_end_reason(barrier)

    def receive_turn(self) -> EndReason | None:
        """Await, validate and absorb the opponent's turn."""
        message = self._await_turn()
        if message is None:
            self.fsm.fail("response timeout")
            self.end_reason = EndReason.TIMEOUT
            return self.end_reason
        self.fsm.to(Phase.VERIFYING)
        problem = absorb_turn(self.state, message, self.event)
        if problem:
            self.fsm.fail(problem)
            self.end_reason = EndReason.TAMPER_FORFEIT
            return self.end_reason
        self.state.full_turns += 1
        decay_after_full_turn(self.state)
        ended = self._opponent_end_reason(message)
        if ended is None:
            self.fsm.to(Phase.WAITING_FOR_OPPONENT)
        return ended

    def _apply_own_action(self, move: Move, barrier: Position | None) -> None:
        """Commit our chosen action to the local world model."""
        if barrier:
            placement = place_barrier(
                self.state.board, self.state.role, self.state.own_position, barrier
            )
            self.state.board = placement.board
            self.state.barriers_used += 1
            self.event("barrier.placed", cell=list(barrier))
        else:
            self.state.own_position = apply_move(self.state.board, self.state.own_position, move)
        self.state.own_scent.deposit(self.state.own_position)

    def _legal_move(self, facts: TurnFacts, legal: tuple[Move, ...]) -> Move:
        """Ask the brain, then hard-filter: an illegal move can never be sent."""
        chosen = self._brain.pick_move(facts)
        if chosen not in legal:
            self.event("move.illegal_rejected", proposed=getattr(chosen, "value", str(chosen)))
            return Move.STAY if Move.STAY in legal else legal[0]
        return chosen

    def _barrier_choice(self, facts: TurnFacts) -> Position | None:
        """Cop-only barrier decision, refused once the quota is spent."""
        if self.state.role is not Role.COP or self.state.barriers_left <= 0:
            return None
        return self._brain.pick_barrier(facts)

    def _capture_claim(self) -> bool:
        """Claim only from our own true cell — never a foreign one (rule 22)."""
        if self.state.role is not Role.COP:
            return False
        return self.state.opponent_estimate == self.state.own_position

    def _commit_and_send(self, payload: dict[str, Any]) -> None:
        """Seal the step and transmit commit + reveal in protocol order."""
        self.fsm.to(Phase.COMMITTING)
        commit = self.state.ledger.commit(self.state.step, payload)
        self._transport.send_turn({"step": self.state.step, "commit": commit})
        self.state.ledger.acknowledge(self.state.step)
        revealed = self.state.ledger.reveal(self.state.step)
        self._transport.send_turn({"step": self.state.step, **revealed})
        self.fsm.to(Phase.AWAITING_REVEAL)
        self.event("turn.sent", commit=commit[:16])

    def _await_turn(self) -> dict[str, Any] | None:
        """Wait for the opponent, retrying within the deadline budget."""
        for attempt in range(self._max_retries):
            message = self._transport.receive_turn(self._timeout)
            if message is not None:
                return message
            self.event("turn.timeout", attempt=attempt + 1, waited=self._timeout)
        return None

    def _own_end_reason(self, barrier: Position | None) -> EndReason | None:
        """Did our own move end the mini-game?"""
        target = self.state.opponent_estimate
        if not (self.state.role is Role.COP and barrier and target):
            return None
        captured = evaluate_barrier_capture(barrier, target).captured
        return self._end(EndReason.CAPTURE) if captured else None

    def _opponent_end_reason(self, message: dict[str, Any]) -> EndReason | None:
        """Did their move (or the clock) end the mini-game?"""
        payload = message.get("payload") or {}
        claimed_us = self.state.opponent_estimate == self.state.own_position
        if self.state.role is Role.THIEF and payload.get("capture_claim") and claimed_us:
            return self._end(EndReason.CAPTURE)
        if self.state.role is Role.COP and self.state.opponent_estimate:
            verdict = evaluate_capture(
                self.state.board, self.state.own_position, self.state.opponent_estimate, True
            )
            if verdict.captured and verdict.reason == "immobilised":
                return self._end(EndReason.CAPTURE)
        params = self.state.board.params
        ended = resolve_survival(self.state.full_turns, params.survival_threshold, params.max_moves)
        return self._end(ended) if ended else None

    def _end(self, reason: EndReason) -> EndReason:
        """Close the mini-game cleanly and open the audit phase."""
        self.end_reason = reason
        if self.fsm.phase is not Phase.GAME_END:
            self.fsm.to(Phase.GAME_END)
        self.state.ledger.open_audit()
        self.event("game.end", reason=reason.value)
        return reason
