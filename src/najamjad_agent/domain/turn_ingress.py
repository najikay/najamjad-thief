"""Absorbing the opponent's turn — the untrusted half of the loop.

Split out of the orchestrator because it has a distinct job and a distinct
threat model: everything here arrives from a competitor over the internet. It
validates their declared step against the agreed physics (there is no referee,
so each peer polices the other), folds the trustworthy parts into our knowledge,
and returns a reason string when the opponent has broken the rules.
"""

from collections.abc import Callable
from typing import Any

from .game_state import GameState
from .movement import validate_opponent_step


def absorb_turn(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> str | None:
    """Fold one opponent message into `state`; return a violation reason or None."""
    payload = message.get("payload") or {}
    commit = message.get("commit")
    step = _step_of(message, state.step)
    if commit:
        state.ledger.record_opponent_commit(step, str(commit))
    if not payload:
        return None
    state.ledger.record_opponent_reveal(step, payload)
    violation = _absorb_position(state, payload, event)
    if violation:
        return violation
    state.last_opponent_hint = str(payload.get("hint", ""))
    state.opponent_scent.absorb(payload.get("smell_grid") or {})
    _absorb_barrier(state, payload, event)
    return None


def _step_of(message: dict[str, Any], fallback: int) -> int:
    """Read the step number defensively — peers send what they like."""
    try:
        return int(message.get("step", fallback))
    except (TypeError, ValueError):
        return fallback


def _parse_cell(raw: Any) -> tuple[int, int] | None:
    """Parse a `[row, col]` wire value, tolerating anything malformed."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


def _absorb_position(
    state: GameState,
    payload: dict[str, Any],
    event: Callable[..., None],
) -> str | None:
    """Police the declared move: one orthogonal step, no walls, no teleports."""
    target = _parse_cell(payload.get("position"))
    if target is None:
        return None
    if state.opponent_estimate is not None:
        violation = validate_opponent_step(state.board, state.opponent_estimate, target)
        if violation:
            event("physics.violation", reason=violation)
            return f"opponent physics violation: {violation}"
    state.opponent_estimate = target
    return None


def _absorb_barrier(
    state: GameState,
    payload: dict[str, Any],
    event: Callable[..., None],
) -> None:
    """Honour a truthfully declared barrier placement (book rules 15-16)."""
    cell = _parse_cell(payload.get("barrier_placed"))
    if cell is not None and state.board.in_bounds(cell):
        state.board = state.board.with_barrier(cell)
        event("barrier.observed", cell=list(cell))


def outgoing_extras(state: GameState, barrier: Any, claim: bool) -> dict[str, Any]:
    """Optional sealed fields carried alongside our move.

    The scent snapshot is what the opponent absorbs; it deliberately contains
    intensities only, never a coordinate, so publishing it leaks evidence but
    not our position.
    """
    extras: dict[str, Any] = {"smell_grid": state.own_scent.snapshot()}
    if barrier:
        extras["barrier_placed"] = [barrier[0], barrier[1]]
    if state.role.value == "police":
        extras["capture_claim"] = claim
    return extras


def decay_after_full_turn(state: GameState) -> None:
    """Advance the world once both agents have moved (FR-ENG-7).

    Decay and the Bayes step belong together: applying them per half-turn would
    age the trail twice as fast as the agreed physics and desynchronise our
    belief from the opponent's own model of the same field.
    """
    state.own_scent.decay_all()
    state.opponent_scent.decay_all()
    state.belief.diffuse()
    observed = {cell: state.opponent_scent.intensity_at(cell) for cell in state.board.cells()}
    state.belief.update_scent(observed)
    state.belief.exclude((state.own_position,))
