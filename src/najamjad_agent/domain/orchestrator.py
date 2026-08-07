"""The Orchestrator — single gateway conducting one mini-game (book rule 3).

Peripheral modules never call each other: the belief engine does not know about
the transport, the strategy does not know about crypto, and the transport knows
nothing about the rules. Everything meets here. That is what makes the whole
turn loop testable against fakes — no network, no LLM, no real clock — which is
precisely the seam Assignment 6 could never exercise.

Ingress handling lives in `turn_ingress` (untrusted input, its own threat
model); this module owns the outgoing half and the end-of-game decision.
"""

from typing import Any

from ..constants import EndReason, Move, Phase, Role
from ..shared.events import Emit
from .crypto import step_payload
from .endings import claim_survival_if_outlasted, opponent_end_reason, own_barrier_capture
from .fsm import GameStateMachine
from .game_state import GameState, TurnFacts
from .movement import apply_move, legal_moves, place_barrier
from .params import Position
from .ports import Brain, Clock, Speaker, Transport
from .turn_egress import build_turn_message, outgoing_extras
from .turn_ingress import absorb_turn, decay_after_full_turn

THIEF_MOVES_FIRST = True
#: Consecutive silent opponent turns before reciprocal emission mirrors them.
#: Three, so a peer whose first turns are quiet while they warm up is not
#: mistaken for one who has chosen to say nothing.
SILENCE_GRACE_TURNS = 3


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
        emit: Emit | None = None,
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
        # Suppressed here, before `step_payload` seals it, so the commitment and
        # the wire carry the same string. Stripping the hint afterwards would
        # leave our own commit describing a turn we did not send, which the audit
        # cannot tell apart from tampering.
        emission = self.state.emission.mirroring(
            self.state.peer_silent_turns >= SILENCE_GRACE_TURNS
        )
        # **Decided before we speak, not after.** `compose` reaches a vendor and
        # costs tokens and latency; blanking its result afterwards paid for both
        # and sent nothing. Against Amjad we spent 23,648 tokens while the peer
        # spent zero — and a run configured to stay silent would have spent them
        # too. Asking the policy first is what makes a quiet match genuinely
        # deterministic rather than merely expensive and mute.
        hint, intent = self._speaker.compose(facts) if emission.hints else ("", "truth")
        hint = emission.hint(hint)
        self._apply_own_action(move, barrier)
        claim_survival_if_outlasted(self.state)
        payload = step_payload(
            step=self.state.step,
            role=self.state.role.value,
            sub_game=self.state.sub_game,
            position=self.state.own_position,
            move=f"MOVE:{move.value}",
            intent=intent,
            hint=hint,
            state=self.state.state_string(),
            extra=outgoing_extras(
                self.state, barrier, self._capture_claim(barrier), emission
            ),
        )
        self._commit_and_send(payload)
        announced = self.state.pending_end
        if announced is not None:
            # The declaration has now gone out with this turn, so both sides
            # close on the same reason at the same point in the game.
            self.state.pending_end = None
            self.event("game.declared", reason=announced.value)
            return self._resolve(announced)
        return self._resolve(own_barrier_capture(self.state, barrier))

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
        ended = self._resolve(opponent_end_reason(self.state, message))
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

    def _capture_claim(self, barrier: Position | None = None) -> Position | None:
        """The cell we are claiming the thief occupies, if we are claiming one.

        Only ever **our own true cell** (rule 22). Claiming a cell we are not
        standing on would let a cop probe the board for free; the disclosure is
        the price of claiming, and it is what makes a speculative claim
        expensive.

        A barrier dropped on the believed thief is therefore *not* claimed here.
        It is declared (rules 15-16), and a thief that finds itself under it
        concedes on its own next turn — which is both the honest mechanism and
        the only one an opponent who does not share our barrier rule can be
        expected to take part in.

        `None` when we are not claiming: an empty claim is not a claim, and the
        opponent should not have to distinguish the two.
        """
        del barrier
        if self.state.role is not Role.COP:
            return None
        target = self.state.opponent_estimate
        return target if target is not None and target == self.state.own_position else None

    def _commit_and_send(self, payload: dict[str, Any]) -> None:
        """Seal the step and transmit only what a peer is entitled to see.

        Our position, move and intent stay sealed until the end-of-game audit.
        What crosses the wire is the commitment plus the evidence the rules make
        public: the scent field we emit involuntarily, our free-language hint,
        any barrier we placed (rule 15 makes declaration mandatory) and a
        capture claim.
        """
        self.fsm.to(Phase.COMMITTING)
        commit = self.state.ledger.commit(self.state.step, payload)
        message = build_turn_message(self.state, commit, payload)
        self._transport.send_turn(message)
        self.state.ledger.acknowledge(self.state.step)
        self.state.ledger.reveal(self.state.step)
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

    def _resolve(self, reason: EndReason | None) -> EndReason | None:
        """Close the mini-game when an end condition fired."""
        return self._end(reason) if reason is not None else None

    def _end(self, reason: EndReason) -> EndReason:
        """Close the mini-game cleanly and open the audit phase."""
        self.end_reason = reason
        if self.fsm.phase is not Phase.GAME_END:
            self.fsm.to(Phase.GAME_END)
        self.state.ledger.open_audit()
        self.event("game.end", reason=reason.value)
        return reason
