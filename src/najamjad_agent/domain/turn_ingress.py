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

from . import cop_sighting
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
    answering = message.get("claim_response") is not None
    if commit and not answering:
        try:
            state.ledger.record_opponent_commit(step, str(commit))
        except ProtocolOrderError as error:
            # A peer re-committing a step it already committed is either buggy
            # or trying to overwrite history. Either way it is their protocol
            # error, reported rather than allowed to crash our turn loop.
            event("peer.duplicate_commit", step=step, reason=str(error))
            return f"opponent protocol error: {error}"
    elif answering:
        # The answer to our capture claim is a *reply*, not a new turn. The
        # reference sends its concession as a final message at the step it is
        # answering, so recording it as a fresh commit reads as a peer
        # overwriting history — and we branded an honest opponent a forger for
        # conceding, filing `tamper_forfeit` against a game they scored as our
        # capture. Two peers disagreeing like that voids it for both.
        event("peer.answered_claim", step=step)

    # A peer that leaks its own position is not a threat to us, but it is worth
    # noticing: either they are running a broken implementation, or baiting us.
    if _has_position(message):
        event("peer.leaked_position", step=step)

    _watch_fair_play(state, step, message, event)
    state.last_opponent_hint = str(message.get("hint", "") or "")
    problems = state.opponent_scent.absorb(message.get("smell_grid") or {})
    for problem in problems:
        event("scent.rejected", reason=problem)
    _absorb_barrier(state, message, event)
    _absorb_capture_claim(state, message, event)
    return None


def _watch_fair_play(
    state: GameState, step: int, message: dict[str, Any], event: Callable[..., None]
) -> None:
    """Record any rule breach in their declared turn — never act on it.

    Observational by design. Deciding a match on our own accusation is the
    contradiction rules 33-35 void both teams for, and an honest peer with an
    off-by-one is far likelier than a cheat. It is checked *before* the barrier
    is absorbed, so the board still shows the position they moved from.
    """
    monitor = state.fair_play
    if monitor is None:
        return
    for finding in monitor.observe(state.board, step, message):
        event("opponent.violation", **finding.as_dict())


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
    """Honour a truthfully declared barrier placement (book rules 15-16).

    The wall goes onto the board, and — new — the *declaration* goes into the
    belief. The Barrier Law is in lieu of moving, on the cop's own cell or one
    orthogonal step from it, so a barrier is a five-cell fix on the cop. We
    banked the wall and threw the fix away, 143 times in one series.
    """
    cell = _parse_cell(message.get("barrier_placed"))
    if cell is not None and state.board.in_bounds(cell):
        state.board = state.board.with_barrier(cell)
        event("barrier.observed", cell=list(cell))
        _record_sighting(state, cop_sighting.from_barrier(state.board, cell, state.step), event)


def _record_sighting(state: GameState, sighting: Any, event: Callable[..., None]) -> None:
    """Hold a sighting for the belief step, after checking it against the last one.

    A claim exactly overrides a barrier seen on the same turn: both can arrive
    together, and the claim is the sharper of the two, so the weaker evidence
    must not be the one that survives.
    """
    if sighting is None:
        return
    checked = cop_sighting.plausible(sighting, state.last_sighting)
    held = state.cop_sighting
    if held is not None and held.exact and not checked.exact:
        return
    state.cop_sighting = checked
    event("cop.sighted", **checked.as_event())


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
    if claim is None or claim is False:
        return
    # The reference sends the cell as the claim itself; our earlier form sent
    # `true` beside a separate `claimed_cell`. Read whichever arrived.
    state.claimed_cell = _parse_cell(claim) or _parse_cell(message.get("claimed_cell"))
    # The answer is decided HERE, against the cell we occupy at the moment the
    # claim is made — not when we get round to replying. Deciding it later meant
    # answering from the cell we had already moved to, so a claim that truly
    # landed was answered "no": a dishonest reply under rules 21-22, and one the
    # audit would expose, for a game we had ourselves recorded as a capture.
    claimed = state.claimed_cell
    state.pending_capture_claim = claimed is not None and tuple(claimed) == tuple(
        state.own_position
    )
    event(
        "capture.claimed",
        step=state.step,
        cell=list(state.claimed_cell or ()),
        lands=state.pending_capture_claim,
    )
    # The claim is the cop's own cell, and the cop said so. `evaluate_capture`
    # scores a capture only when the cop *occupies* the cell it claims, so a
    # truthful claim is an exact position fix — and an untruthful one is provable
    # at the audit, which is what makes it safe to believe. This is the strongest
    # evidence a silent opponent hands us, and it was going straight into a
    # capture check and nowhere else.
    if claimed is not None:
        _record_sighting(state, cop_sighting.from_claim(claimed, state.step), event)


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
    _fuse_sighting(state)
    state.belief.exclude((state.own_position,))
    # With no transmitted position, our estimate of them IS our belief peak.
    state.opponent_estimate = state.belief.peak()


def _fuse_sighting(state: GameState) -> None:
    """Apply this turn's declared-position evidence, after diffusion and scent.

    The ordering is the whole point and it is the same ordering scent already
    uses. `diffuse` models the move the opponent just made, which necessarily
    smears a point observation across five cells; the observation is then fused
    *on top* to say where that move landed. Fusing before the diffusion instead
    would leave the belief peaked on a neighbour of the true cell — and a thief
    keeping its distance-2 invariant from a cell one step off the cop is a thief
    standing next to the cop, which is a capture.

    Applied after `update_scent` for the same reason it is applied at all: a
    declaration is a direct statement of position, and the scent likelihood is an
    inference from a decaying field. When both are present the direct statement
    should win, and against a silent opponent it is the only one there is.
    """
    sighting = state.cop_sighting
    state.cop_sighting = None
    if sighting is None:
        return
    state.belief.observe_reach(sighting.cells, sighting.confidence)
    state.last_sighting = sighting
