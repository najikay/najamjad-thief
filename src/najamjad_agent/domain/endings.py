"""Deciding when a mini-game is over.

Separated from the orchestrator because the conditions are rules, not
conducting: a capture claim that lands, a barrier dropped on the thief, a thief
with nowhere left to go, or the survival clock running out. Keeping them here
means the turn loop reads as a sequence of steps rather than a thicket of
end-of-game special cases.
"""

from typing import Any

from ..constants import EndReason, Role
from .capture import evaluate_barrier_capture, is_immobilised, resolve_survival
from .game_state import GameState
from .params import Position


def return_reason(reason: EndReason) -> EndReason:
    """Identity helper so callers read as `return return_reason(...)`."""
    return reason


def own_barrier_capture(state: GameState, barrier: Position | None) -> EndReason | None:
    """Whether a barrier we just placed ends the mini-game. It never does.

    We used to end the game here, on `opponent_estimate` — our *belief* about
    where the thief is. Against ourselves that agreed, because our own thief
    concedes a barrier trap from its true cell and both sides reached the same
    verdict. Against the course reference it did not: its thief has no concept
    of losing by being walled in, so it kept playing while we closed the game,
    filed the capture, and then read its silence at audit time as tampering.

    A capture is a *claim the thief confirms* (rules 21-22). One we conclude
    from a guess is worth nothing even when the guess is right: a game the
    opponent does not agree ended is void for both of us (rules 33-35), which
    scores zero — strictly worse than playing on and taking the survival.

    So the barrier is placed, declared (rules 15-16), and the thief decides. If
    it really is trapped and says so, `_their_declaration` closes the game on
    their word; if it says nothing, the game runs to its horizon.
    """
    del state, barrier
    return None

def opponent_end_reason(state: GameState, message: dict[str, Any]) -> EndReason | None:
    """Did their move (or the clock) end the mini-game?

    An ending we can only see from our own side is *deferred*, not returned: it
    goes into `state.pending_end`, gets announced on one final sealed turn, and
    closes the game only then. Closing immediately is what made the two peers
    file contradictory reports for the same mini-game.
    """
    declared = _their_declaration(state, message)
    if declared is not None:
        return return_reason(declared)
    if state.role is Role.THIEF and _barrier_traps_us(state, message):
        # Rules 15-16 make the barrier declaration mandatory, so we can evaluate
        # it from our own true cell the moment it arrives. But we must *say so*
        # rather than simply closing: the cop no longer concludes a barrier
        # capture from its own belief, so a silent concession leaves it waiting
        # out the deadline against a game we have already ended.
        #
        # The concession travels as an answered capture claim — "your barrier
        # landed on me" — because that is the one shape every implementation
        # reads as a police capture. A `win_claim` would not do: in the
        # reference's protocol a win claim from the thief means the *thief* won.
        #
        # The cell we name has to be the one that is *true*. For rule 46 the
        # barrier landed on us, so the barrier cell and ours are the same and
        # either would do. For a rule 47 immobilisation they are different —
        # the wall took our last exit without touching us — and naming the
        # barrier cell would be conceding to a capture that did not happen, at
        # a cell we do not occupy. Rules 18-22 require the answer to be honest,
        # and the sealed record would show it was not. Conceding our own cell
        # costs nothing: the mini-game is over either way.
        state.claimed_cell = state.own_position
        state.pending_capture_claim = True
        state.pending_end = EndReason.CAPTURE
    if state.role is Role.THIEF and message.get("capture_claim"):
        # Rules 21-22: answered from our own true cell, and honestly. The claim
        # names a cell, so it lands only if that cell is ours.
        claimed = state.claimed_cell
        if claimed is not None and tuple(claimed) == tuple(state.own_position):
            state.pending_end = EndReason.CAPTURE
    # A cop used to conclude an immobilisation capture here, from
    # `opponent_estimate` — a belief the thief never confirmed. It is gone for
    # the same reason as the barrier capture in `own_barrier_capture`, plus a
    # sharper one: this ending was *announced* as a `win_claim`, and in the
    # reference's protocol a `win_claim` means the **thief** won. Declaring a
    # cop capture that way would have had the opponent record a thief victory.
    params = state.board.params
    survived = resolve_survival(state.full_turns, params.survival_threshold, params.max_moves)
    if survived is not None and state.pending_end is None:
        state.pending_end = survived
    return None


def _their_declaration(state: GameState, message: dict[str, Any]) -> EndReason | None:
    """The ending the opponent has told us about, if any.

    Their announcement is authoritative for closing our side: it is the only
    way we learn about an ending only they could see — whether our capture
    claim landed, or that they have outlasted the survival clock.
    """
    if state.role is Role.COP and _answer_says_caught(message.get("claim_response")):
        return EndReason.CAPTURE
    claimed = _win_type(message.get("win_claim"))
    if claimed:
        try:
            return EndReason(claimed)
        except ValueError:
            return None
    return None


def _answer_says_caught(answer: Any) -> bool:
    """Did the thief's answer confirm our claim landed?

    The reference answers `{"claim": [r, c], "caught": bool}`; our earlier form
    was a bare boolean. Both are understood.
    """
    if isinstance(answer, dict):
        return answer.get("caught") is True
    return answer is True


def _win_type(claim: Any) -> str:
    """The ending an opponent declared, from either shape it may arrive in."""
    if isinstance(claim, dict):
        return str(claim.get("type") or "")
    return claim if isinstance(claim, str) else ""


def _barrier_traps_us(state: GameState, message: dict[str, Any]) -> bool:
    """Did the barrier they just declared end the game for us?

    Two ways it can, and only the first was ever checked:

    * **rule 46** — the wall lands on the cell we occupy;
    * **rule 47** — the wall takes our last exit, leaving no move but STAY.

    The second is why `capture.evaluate_capture` existed with no caller: rule 47
    was implemented, unit-tested, used by the duel harness, and never evaluated
    in a live game. A thief sealed into a pocket played on as though nothing had
    happened, while the cop scored a capture — and two peers filing different
    outcomes for one mini-game is what rules 33-35 void for both.

    Asked of `own_position` and the freshly-absorbed board, which is the only
    version of this we may ask. The cop deliberately no longer concludes an
    immobilisation from `opponent_estimate`, because that is a belief the thief
    never confirmed; the thief knows its own cell truthfully, so the thief is
    the side that can answer honestly. `mobile_only` is the whole point — STAY
    is never blocked, so an ordinary legal-move check can never see this.
    """
    cell = message.get("barrier_placed")
    if not (isinstance(cell, list | tuple) and len(cell) == 2):
        return False
    if evaluate_barrier_capture(tuple(cell), state.own_position).captured:
        return True
    return is_immobilised(state.board, state.own_position)


def claim_survival_if_outlasted(state: GameState) -> None:
    """As thief, declare survival on the very move that reaches the horizon.

    This has to happen on *our own* turn, not while absorbing theirs. The
    opponent's police loop ends a game only when the thief announces a win; our
    silence is read as `timeout` and scores 0-0 for both, which under rules
    33-35 is a disagreement that voids the game.

    Absorbing an incoming turn was too late in two ways. It counted
    `full_turns`, which is incremented *after* the check, and by the time the
    horizon was reached the turn loop had no iteration left to send the
    announcement in — so we recorded survival privately and told nobody. Our own
    series never caught it because every game we played ended in a capture.

    The opponent's rule is `step_number >= max_steps` evaluated straight after
    applying its move, so the counter and the moment both match here.
    """
    if state.role is not Role.THIEF or state.pending_end is not None:
        return
    params = state.board.params
    outlasted = resolve_survival(state.step, params.survival_threshold, params.max_moves)
    if outlasted is not None:
        state.pending_end = outlasted
