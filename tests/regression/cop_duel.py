"""Run our cop against a scripted thief, with the belief it would genuinely hold.

`duel.py` is the thief-side instrument: our brain evades a scripted cop. This is
its mirror, and the project needed one the moment a counted series was lost as
cop rather than as thief.

**The belief is built by the real ingress path, not handed over.** A cop-side
harness that simply told the brain where the thief was would measure the move
policy and nothing else — and the 2026-08-14 loss was not a move-policy failure.
Our cop tracked vibecode to Manhattan distance 2 by step 6 and then held exactly
2 for the remaining 28 steps, never once reaching 1, while placing 3 barriers of
14. Both halves of that need reproducing to be worked on: the tracking that
succeeded and the walling that did not.

So the thief's scent goes through `ScentField` at the agreed physics, onto the
wire shape a peer actually sends, and into `absorb_turn` /
`decay_after_full_turn` exactly as a match would. What comes back out is the
distribution our cop really sees — including how much mass sits on the peak,
which is the number `cop_barriers.plan_barrier` is denominated in and the reason
it declined eleven walls.

Emission is modelled on what vibecode verifiably transmit: a field centred on
their true cell, **post-decay** (peak 0.8 against our pre-decay 0.9), verified
honest 35 frames of 35 against their own revealed positions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.capture import is_immobilised
from najamjad_agent.domain.game_state import GameState
from najamjad_agent.domain.ledger import CommitLedger
from najamjad_agent.domain.movement import apply_move, legal_moves, place_barrier
from najamjad_agent.domain.params import GameParams, Position
from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.turn_ingress import absorb_turn, decay_after_full_turn
from najamjad_agent.strategy.territory import distances_from


@dataclass
class CopResult:
    """What one replayed mini-game did, from the cop's side."""

    captured: bool
    step: int
    barriers: tuple[Position, ...] = ()
    #: Manhattan distance to the true thief cell, per step.
    distances: tuple[int, ...] = ()
    #: Probability mass on the belief peak, per step — the quantity
    #: `plan_barrier`'s threshold is actually denominated in.
    peak_mass: tuple[float, ...] = ()
    #: Whether the belief peak was the thief's true cell, per step.
    peak_correct: tuple[bool, ...] = ()
    #: Where the thief actually went, so parking is measurable.
    thief_path: tuple[Position, ...] = ()
    reason: str = ""
    events: list[str] = field(default_factory=list)

    @property
    def barriers_used(self) -> int:
        return len(self.barriers)

    @property
    def tracking(self) -> float:
        """Share of steps on which the belief peak named the true cell."""
        return sum(self.peak_correct) / max(1, len(self.peak_correct))


class Facts:
    """The read-only view the cop brain is given, matching the orchestrator's.

    `legal` is computed from the board, not assumed to be all five moves. Handing
    the brain every move made it walk into its own barrier on the first run of
    this harness — a harness kinder than the orchestrator, which filters, and
    exactly the class of double this repo has been bitten by before.
    """

    def __init__(self, state: GameState, belief: dict[Position, float], left: int) -> None:
        self.board = state.board
        self.own_position = state.own_position
        self.belief = belief
        self.scent = {cell: state.opponent_scent.intensity_at(cell) for cell in state.board.cells()}
        self.own_scent = {cell: state.own_scent.intensity_at(cell) for cell in state.board.cells()}
        self.legal = legal_moves(state.board, state.own_position)
        self.barriers_left = left
        self.role = "police"
        self.step = state.step
        self.steps_remaining = max(0, state.board.params.max_moves - state.step)
        self.sub_game = 1


def _their_frame(cell: Position, params: GameParams) -> dict[str, float]:
    """The grid a scent-emitting peer sends from `cell`, post-decay.

    Built with the real `ScentField` at the agreed physics rather than a
    hand-rolled blob, so the shape our belief consumes is the shape a peer
    actually puts on the wire.
    """
    field_ = ScentField(board_size=params.grid_size)
    field_.deposit(cell)
    field_.decay_all()
    return field_.snapshot()


def run_cop_duel(
    brain: Any,
    thief_line: Sequence[Position],
    params: GameParams,
    emits_scent: bool = True,
    thief_brain: Any = None,
) -> CopResult:
    """Replay `thief_line` against `brain` and report whether the cop closed.

    Each step runs thief-moves, then cop-decides, mirroring the orchestrator's
    order. The cop either moves or places a barrier — never both, per the
    Barrier Law — and an illegal move is filtered exactly as the orchestrator
    filters it, so a scoring change cannot hide behind one.
    """
    board = Board(params)
    state = GameState(
        board=board, role=Role.COP, sub_game=1, own_position=params.cop_start,
        belief=BeliefGrid(board, start=params.thief_start),
        own_scent=ScentField(board_size=board.size),
        opponent_scent=ScentField(board_size=board.size),
        ledger=CommitLedger(sub_game=1),
    )
    # The thief's own view of us, built the same way ours is built of them: our
    # scent through the real ingress path. A point mass would hand it certainty
    # no opponent has, and an empty dict drops it into its blind fallback — the
    # two errors bracket the truth and neither is it.
    theirs = GameState(
        board=board, role=Role.THIEF, sub_game=1, own_position=params.thief_start,
        belief=BeliefGrid(board, start=params.cop_start),
        own_scent=ScentField(board_size=board.size),
        opponent_scent=ScentField(board_size=board.size),
        ledger=CommitLedger(sub_game=1),
    )
    walls: list[Position] = []
    path: list[Position] = []
    distances: list[int] = []
    masses: list[float] = []
    correct: list[bool] = []
    events: list[str] = []
    horizon = min(params.survival_threshold, params.max_moves)

    thief = tuple(params.thief_start)
    for step in range(1, horizon + 1):
        if thief_brain is None:
            thief = tuple(thief_line[min(step - 1, len(thief_line) - 1)])
        else:
            # The thief moves first, as the book requires, and sees the cop —
            # which overstates its knowledge and therefore understates our cop.
            # A pursuit policy that cannot close on a thief with perfect
            # information will not close on one with imperfect information.
            # **A real belief, not an empty dict.** `ThiefBrain` reads
            # `facts.belief` and nothing else — handed `{}` it decides
            # `_cop_cell` is unknown and plays its *blind* fallback, so every
            # thief measurement taken through this harness was of a policy that
            # could not see the cop. A point mass on the cop's true cell
            # overstates the thief's knowledge and therefore understates our
            # cop, which is the safe direction for a cop benchmark.
            theirs.own_position = thief
            theirs.step = step
            theirs.board = state.board
            absorb_turn(theirs, {"step": step, "sender": "police",
                                 "commit": f"{step:064x}",
                                 "smell_grid": _their_frame(state.own_position, params)},
                        lambda name, **_f: None)
            decay_after_full_turn(theirs)
            facts_t = Facts(theirs, theirs.belief.as_dict(), 0)
            facts_t.own_position = thief
            facts_t.legal = legal_moves(state.board, thief)
            facts_t.cop_position = state.own_position
            move_t = thief_brain.pick_move(facts_t)
            if move_t in facts_t.legal:
                row, col = state.board.delta_for(move_t)
                landing = (thief[0] + row, thief[1] + col)
                if state.board.is_open(landing):
                    thief = landing
        state.step = step
        message: dict[str, Any] = {"step": step, "sender": "thief", "commit": f"{step:064x}"}
        if emits_scent:
            message["smell_grid"] = _their_frame(thief, params)
        absorb_turn(state, message, lambda name, **_f: events.append(name))
        decay_after_full_turn(state)

        belief = state.belief.as_dict()
        peak = state.belief.peak()
        masses.append(belief.get(peak, 0.0) if peak else 0.0)
        correct.append(peak == thief)
        distances.append(Board.manhattan(state.own_position, thief))
        path.append(thief)

        if state.own_position == thief:
            return CopResult(True, step, tuple(walls), tuple(distances), tuple(masses),
                             tuple(correct), tuple(path), "captured", events)

        facts = Facts(state, belief, params.max_barriers - len(walls))
        wall = brain.pick_barrier(facts) if len(walls) < params.max_barriers else None
        if wall is not None:
            placement = place_barrier(state.board, Role.COP, state.own_position, wall)
            state.board = placement.board
            walls.append(tuple(wall))
            # **A barrier on the thief's cell does NOT end the game**, and a
            # harness that says otherwise is measuring a rule no opponent
            # implements. `domain/endings.own_barrier_capture` returns None for
            # exactly this reason: the course reference has no barrier-capture
            # and no immobilisation check at all, so it plays on while we close
            # the game, file the capture, and read its silence at audit time as
            # tampering — a contradiction that voids the mini-game for both
            # sides (rules 33-35) and scores worse than the survival we gave up.
            #
            # Every opponent we have met is reference-derived. The only capture
            # they honour is co-location plus a claim, which their `is_captured`
            # answers from their own sealed position. Barriers therefore *shrink
            # the board* and never take the thief; the taking is always the
            # claim below.
            #
            # **An immobilised thief is still scored, in two honest grades.**
            # Not scoring it at all is how this bench spent 2026-08-20 calling
            # `walls=12 smallest_room=1` a survival. A thief with zero exits
            # beside a cop that can reach its cell is dead in every rulebook —
            # the cop simply steps on and claims, so it counts as a capture
            # (the walk costs the steps the distance says). Sealed *away* from
            # us it is a rule-47 win only, which the filing layer refuses to
            # claim against a reference peer — reported as `remote seal`,
            # deliberately NOT `captured`, so a plan that manufactures those
            # cannot green-light itself.
            if is_immobilised(state.board, thief):
                gap = distances_from(state.board, state.own_position).get(thief)
                if gap is not None and step + gap <= horizon:
                    return CopResult(True, step + gap, tuple(walls), tuple(distances),
                                     tuple(masses), tuple(correct), tuple(path),
                                     "captured (immobilised, walked onto)", events)
                return CopResult(False, step, tuple(walls), tuple(distances),
                                 tuple(masses), tuple(correct), tuple(path),
                                 "remote seal (rule 47 only)", events)
        else:
            # The orchestrator hard-filters an illegal move rather than trusting
            # the brain, and so must this: a scoring regression must not be able
            # to hide behind an escape the real agent could never make.
            move = brain.pick_move(facts)
            if move not in facts.legal:
                move = Move.STAY if Move.STAY in facts.legal else facts.legal[0]
            state.own_position = apply_move(state.board, state.own_position, move)
            # **Landing on the thief is a capture, and this is where the game is
            # actually decided.** The check used to exist only before the cop
            # moved, which catches the thief walking into a stationary cop and
            # nothing else — so a reactive thief could never be taken here, and
            # every cop measurement made through this harness was of a pursuit
            # that was not allowed to finish. It ran the cop at distance 1 for
            # 23 consecutive steps against the greedy evader and scored it a
            # survival.
            #
            # Settled from real games rather than from the rule text, because
            # the rule text is what the earlier reading came from. In the
            # moaamoha series of 2026-08-15 our cop captured three times and our
            # thief was captured twice, and **all five were this move**: the
            # thief moves first, the cop steps onto the cell it moved to, and
            # claims it. g02 [6,6]->[5,6] with our cop [5,5]->[5,6]; g04
            # [6,6]->[6,5] against [5,5]->[6,5]; g06 [6,4]->[6,3] against
            # [5,3]->[6,3]; and the two we lost are the same geometry from the
            # other side. Their `is_captured` answers the claim from the sealed
            # position of that step, so the cell the thief just moved to is
            # exactly what a claim is compared against.
            if state.own_position == thief:
                return CopResult(True, step, tuple(walls), tuple(distances), tuple(masses),
                                 tuple(correct), tuple(path), "captured", events)
        state.own_scent.deposit(state.own_position)

    return CopResult(False, horizon, tuple(walls), tuple(distances), tuple(masses),
                     tuple(correct), tuple(path), "thief survived", events)
