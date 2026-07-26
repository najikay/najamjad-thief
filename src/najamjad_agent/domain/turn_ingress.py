"""Absorbing the opponent's turn — the untrusted half of the loop.

Split out of the orchestrator because it has a distinct job and a distinct
threat model: everything here arrives from a competitor over the internet.

What a peer legitimately sends us is deliberately thin. Their position and move
stay sealed inside their commitment until the end-of-game audit, so we learn
where they are only from evidence the rules make public:

* the **scent field** they emit involuntarily and cannot fake (book PAGE 22);
* a **free-language hint** that may be a lie;
* any **barrier** the cop placed, which must be declared truthfully (rule 15);
* a **capture claim**, which the thief must answer honestly (rules 21-22).

Because positions are not transmitted, per-turn physics policing is impossible
by design — an illegal move is caught at the audit, where the full sealed
record is finally revealed and re-hashed. That is the book's own trade-off:
hidden information now, verifiable honesty later.
"""

from collections.abc import Callable
from typing import Any

from .game_state import GameState
from .ledger import ProtocolOrderError


def absorb_turn(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> str | None:
    """Fold one opponent message into `state`; return a violation reason or None."""
    step = _step_of(message, state.step)
    commit = message.get("commit")
    if commit:
        try:
            state.ledger.record_opponent_commit(step, str(commit))
        except ProtocolOrderError as error:
            # A peer re-committing a step it already committed is either buggy
            # or trying to overwrite history. Either way it is their protocol
            # error, reported rather than allowed to crash our turn loop.
            event("peer.duplicate_commit", step=step, reason=str(error))
            return f"opponent protocol error: {error}"

    # A peer that leaks its own position is not a threat to us, but it is worth
    # noticing: either they are running a broken implementation, or baiting us.
    if _has_position(message):
        event("peer.leaked_position", step=step)

    state.last_opponent_hint = str(message.get("hint", "") or "")
    problems = state.opponent_scent.absorb(message.get("smell_grid") or {})
    for problem in problems:
        event("scent.rejected", reason=problem)
    _absorb_barrier(state, message, event)
    _absorb_capture_claim(state, message, event)
    return None


def _step_of(message: dict[str, Any], fallback: int) -> int:
    """Read the step number defensively — peers send what they like."""
    try:
        return int(message.get("step", fallback))
    except (TypeError, ValueError):
        return fallback


def _has_position(message: dict[str, Any]) -> bool:
    """True when a peer sent coordinates the protocol does not ask for."""
    payload = message.get("payload")
    if isinstance(payload, dict) and "position" in payload:
        return True
    return "position" in message


def _parse_cell(raw: Any) -> tuple[int, int] | None:
    """Parse a `[row, col]` wire value, tolerating anything malformed."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


def _absorb_barrier(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> None:
    """Honour a truthfully declared barrier placement (book rules 15-16)."""
    cell = _parse_cell(message.get("barrier_placed"))
    if cell is not None and state.board.in_bounds(cell):
        state.board = state.board.with_barrier(cell)
        event("barrier.observed", cell=list(cell))


def _absorb_capture_claim(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> None:
    """Record a cop's capture claim so the thief can answer it truthfully.

    A claim must name the cell it asserts, because otherwise the thief — who
    does not know where the cop is — could not answer honestly at all. That
    disclosure is the price of claiming: a false claim hands us the cop's exact
    position for nothing, which is what makes bluffed claims expensive.
    """
    claim = message.get("capture_claim")
    if not isinstance(claim, bool) or not claim:
        return
    state.pending_capture_claim = True
    state.claimed_cell = _parse_cell(message.get("claimed_cell"))
    event("capture.claimed", step=state.step, cell=list(state.claimed_cell or ()))


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
    elif state.pending_capture_claim:
        # Rules 21-22: a claim must be answered, and answered honestly. Without
        # this the cop never learns whether its claim landed — it waits out the
        # deadline and records a timeout for a game the thief has recorded as a
        # capture, and two contradictory reports void the game for both (rules
        # 33-35). The answer is sealed like everything else, so a lie here is
        # provable at the audit.
        extras["claim_response"] = _claim_lands(state)
        state.pending_capture_claim = None
    if state.pending_end is not None and "claim_response" not in extras:
        # An ending only we can see — survival, or an immobilised thief. Declare
        # it so the opponent closes on the same reason instead of timing out.
        extras["win_claim"] = state.pending_end.value
    return extras


def _claim_lands(state: GameState) -> bool:
    """Whether the cop's claimed cell really is ours."""
    claimed = state.claimed_cell
    return claimed is not None and tuple(claimed) == tuple(state.own_position)


def build_turn_message(
    state: GameState, commit: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """What a peer is entitled to see: the commitment and public evidence.

    Deliberately the mirror image of `absorb_turn`. Position, move and intent
    stay sealed until the audit; everything included here is either unfakeable
    (scent), free-language (the hint), or mandatory to declare (a barrier, a
    capture claim naming the cell it asserts).
    """
    message: dict[str, Any] = {
        "step": state.step,
        "sender": state.role.value,
        "commit": commit,
        "hint": payload.get("hint", ""),
        "smell_grid": payload.get("smell_grid", {}),
    }
    if "barrier_placed" in payload:
        message["barrier_placed"] = payload["barrier_placed"]
    if "capture_claim" in payload:
        message["capture_claim"] = payload["capture_claim"]
        if payload["capture_claim"]:
            # Claiming necessarily discloses where we stand; that cost is what
            # stops a cop claiming speculatively every turn.
            message["claimed_cell"] = list(state.own_position)
    if "claim_response" in payload:
        message["claim_response"] = payload["claim_response"]
    if payload.get("win_claim"):
        message["win_claim"] = payload["win_claim"]
    return message


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
    # With no transmitted position, our estimate of them IS our belief peak.
    state.opponent_estimate = state.belief.peak()
