"""The two things the rules force an opponent to say out loud, read as evidence.

Split from `turn_ingress` at the file budget, and the seam is a real one:
everything in that module is about *absorbing* a peer's turn, while everything
here is about the narrow subset of it the book makes mandatory and truthful.

Positions are not transmitted, so these declarations are the only place an
opponent's location becomes public before the audit:

* a **barrier** (rules 15-16), which the cop must declare truthfully and place
  on its own cell or one orthogonal step from it — a five-cell fix;
* a **capture claim** (rules 21-22), which names a cell, and which every
  implementation in this league fills with the claimer's own position — an
  exact fix. See `cop_sighting.from_claim` for how that was established and
  what it is worth.

Both feed `cop_sighting`, which decides how much each is believed. Neither is
ever acted on as an accusation: deciding a match on our own reading of a peer's
declaration is the contradiction rules 33-35 void both teams for.
"""

from collections.abc import Callable
from typing import Any

from ..constants import Role
from . import cop_sighting
from .game_state import GameState
from .params import Position


def step_of(message: dict[str, Any], fallback: int) -> int:
    """Read the step number defensively — peers send what they like."""
    try:
        return int(message.get("step", fallback))
    except (TypeError, ValueError):
        return fallback


def parse_cell(raw: Any) -> tuple[int, int] | None:
    """Parse a `[row, col]` wire value, tolerating anything malformed."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


def absorb_barrier(
    state: GameState,
    message: dict[str, Any],
    event: Callable[..., None],
) -> None:
    """Honour a truthfully declared barrier placement (book rules 15-16).

    The wall goes onto the board, and the *declaration* goes into the belief.
    The Barrier Law is in lieu of moving, on the cop's own cell or one
    orthogonal step from it, so a barrier is a five-cell fix on the cop. We
    banked the wall and threw the fix away, 143 times in one series.

    **The budget is enforced here, and this is the one place it can be.**
    `movement.place_barrier` refuses our own placement past `max_barriers`, but
    nothing checked theirs, so we banked every wall a peer cared to declare —
    a bare board accepted 46. Only the cop places barriers, so in any mini-game
    every wall came from one side and the board total is the right comparison.

    **No opponent has actually done this.** Counting `barrier.observed` per
    mini-game across the archive gives a maximum of exactly 14, in none of 31
    recorded games above it; the 48 sometimes quoted is a *series* total across
    six games and is not a violation. So this is a guard against a peer we have
    not met, sitting exactly on the boundary real peers reach — which is why it
    refuses only the 15th and why the event carries both counts.

    Refusing the excess is self-defence, not an accusation, and the difference
    matters because everything else in this module is deliberately
    observational. An over-budget wall is not merely noise: honoured, it lets a
    peer seal us into immobilisation, which rule 47 scores as a capture.

    It is not free either, and the trade is worth stating. A refused wall makes
    our board diverge from theirs, after which a move we compute as legal may be
    illegal on their board — a rules 33-35 dispute. We take that trade because
    the alternative is losing the mini-game outright to a peer who can simply
    keep declaring, and because the divergence only begins after they have
    already broken the agreed quota. `fair_play` still sees the declaration, and
    the event carries the evidence.
    """
    cell = parse_cell(message.get("barrier_placed"))
    if cell is None or not state.board.in_bounds(cell):
        return
    agreed = state.board.params.max_barriers
    if state.board.barrier_count >= agreed:
        event("barrier.over_budget", cell=list(cell), agreed=agreed,
              standing=state.board.barrier_count)
        return
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
    # `elapsed` matters and defaulting it to 1 quietly broke the case this
    # module was built for: `last_sighting` deliberately outlives the turn,
    # so against a peer who declares rarely the gap can be ten turns, and a
    # one-step budget then rules their next honest claim implausible.
    previous = state.last_sighting
    elapsed = max(1, state.step - previous.step) if previous is not None else 1
    checked = cop_sighting.plausible(sighting, previous, elapsed)
    held = state.cop_sighting
    if held is not None and held.exact and not checked.exact:
        return
    state.cop_sighting = checked
    event("cop.sighted", **checked.as_event())


def absorb_capture_claim(
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
    state.claimed_cell = parse_cell(claim) or parse_cell(message.get("claimed_cell"))
    if state.claimed_cell is not None:
        # As sent, before it is read as evidence. `scent_audit.verify_trail`
        # compares it against the cell they reveal at the audit, which is the
        # only check that keeps "a claim names the claimer's own cell" a
        # measurement rather than a premise we inherited from the reference.
        state.opponent_frames.record_claim(step_of(message, state.step), state.claimed_cell)
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
    _fix_the_cop_from(state, claimed, event)


def _fix_the_cop_from(
    state: GameState,
    claimed: Position | None,
    event: Callable[..., None],
) -> None:
    """Read the claim as a position fix on the cop — see `cop_sighting.from_claim`.

    **Only when we are the thief.** Capture claims are a police-only declaration,
    so a peer sending one while playing thief is not disclosing anything; it is
    injecting a phantom into the belief we are using to hunt it. `endings.py`
    already gates its own claim handling on the role and this mirrors that.

    **Never a claim on the cell we occupy.** If it is honest we have been caught
    and the belief no longer decides anything; if it is not, it is the one attack
    that costs the opponent nothing, because our own scent field hands them our
    exact cell for free. Dropping it *here*, rather than letting `observe_reach`
    place mass that the turn's closing `exclude()` deletes, is the whole of the
    difference: held, it would first evict any barrier sighting for the same
    turn under `_record_sighting`'s exact-beats-inexact rule, and *that* was the
    blinding both removals recorded. Measured on the archived lines, an opponent
    claiming our cell every turn now leaves the belief exactly where ignoring
    claims leaves it (mean error 2.04) instead of degrading it to 3.73.
    """
    if state.role is not Role.THIEF or claimed is None:
        return
    if tuple(claimed) == tuple(state.own_position):
        event("capture.claim_on_our_own_cell", step=state.step, cell=list(claimed))
        return
    _record_sighting(state, cop_sighting.from_claim(claimed, state.step), event)
