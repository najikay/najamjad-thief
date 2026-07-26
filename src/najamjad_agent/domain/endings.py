"""Deciding when a mini-game is over.

Separated from the orchestrator because the conditions are rules, not
conducting: a capture claim that lands, a barrier dropped on the thief, a thief
with nowhere left to go, or the survival clock running out. Keeping them here
means the turn loop reads as a sequence of steps rather than a thicket of
end-of-game special cases.
"""

from typing import Any

from ..constants import EndReason, Role
from .capture import evaluate_barrier_capture, evaluate_capture, resolve_survival
from .game_state import GameState
from .params import Position


def return_reason(reason: EndReason) -> EndReason:
    """Identity helper so callers read as `return return_reason(...)`."""
    return reason


def own_barrier_capture(state: GameState, barrier: Position | None) -> EndReason | None:
    """Did our own move end the mini-game?"""
    target = state.opponent_estimate
    if not (state.role is Role.COP and barrier and target):
        return None
    captured = evaluate_barrier_capture(barrier, target).captured
    return return_reason(EndReason.CAPTURE) if captured else None

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
    if state.role is Role.THIEF and message.get("capture_claim"):
        # Rules 21-22: answered from our own true cell, and honestly. The claim
        # names a cell, so it lands only if that cell is ours.
        claimed = state.claimed_cell
        if claimed is not None and tuple(claimed) == tuple(state.own_position):
            state.pending_end = EndReason.CAPTURE
    if state.role is Role.COP and state.opponent_estimate:
        verdict = evaluate_capture(
            state.board, state.own_position, state.opponent_estimate, True
        )
        if verdict.captured and verdict.reason == "immobilised":
            state.pending_end = EndReason.CAPTURE
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
    if state.role is Role.COP and message.get("claim_response") is True:
        return EndReason.CAPTURE
    claimed = message.get("win_claim")
    if isinstance(claimed, str) and claimed:
        try:
            return EndReason(claimed)
        except ValueError:
            return None
    return None
