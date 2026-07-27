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
from datetime import UTC, datetime
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


def outgoing_extras(state: GameState, barrier: Any, claim: Any = None) -> dict[str, Any]:
    """Optional sealed fields carried alongside our move.

    The scent snapshot is what the opponent absorbs; it deliberately contains
    intensities only, never a coordinate, so publishing it leaks evidence but
    not our position.
    """
    extras: dict[str, Any] = {"smell_grid": state.own_scent.snapshot()}
    if barrier:
        extras["barrier_placed"] = [barrier[0], barrier[1]]
    if state.role.value == "police":
        if claim is not None:
            # The cell, not a boolean. The reference does `tuple(capture_claim)`
            # to compare it against the thief's true position, so a bare `true`
            # raises in its process — and a claim it cannot read is a capture it
            # can never confirm. We send nothing at all when we are not
            # claiming, rather than a falsy value.
            extras["capture_claim"] = [claim[0], claim[1]]
    elif state.pending_capture_claim is not None:
        # Rules 21-22: a claim must be answered, and answered honestly. Without
        # this the cop never learns whether its claim landed — it waits out the
        # deadline and records a timeout for a game the thief has recorded as a
        # capture, and two contradictory reports void the game for both (rules
        # 33-35). The answer is sealed like everything else, so a lie here is
        # provable at the audit.
        #
        # `is not None`, not truthiness: an honest "no" is False, and a falsy
        # check would silently swallow exactly the answers we are obliged to give.
        # The reference's shape: the cell claimed, and whether it landed. Richer
        # than a bare boolean, and it lets the cop check the answer refers to
        # the claim it actually made.
        extras["claim_response"] = {
            "claim": list(state.claimed_cell or ()),
            "caught": bool(state.pending_capture_claim),
        }
        state.pending_capture_claim = None
    if state.pending_end is not None and not _admitting_capture(extras):
        # An ending only we can see — survival, or an immobilised thief. Declare
        # it so the opponent closes on the same reason instead of timing out.
        #
        # This used to be suppressed whenever a `claim_response` was present at
        # all, which looked cautious and was wrong. The reference's police
        # attaches a `capture_claim` to *every* move it makes, so our thief
        # almost always owes it an answer — and the two fields together meant we
        # never once declared survival on the wire. It reached the horizon,
        # recorded survival privately, and its opponent timed the game out.
        #
        # The fields are independent in the reference's handler, and a capture
        # already outranks a survival there, so the only answer that must
        # silence the declaration is one admitting we were caught.
        extras["win_claim"] = {"type": state.pending_end.value}
    return extras


def _admitting_capture(extras: dict[str, Any]) -> bool:
    """Whether this turn concedes a capture, which outranks any win we claim."""
    answer = extras.get("claim_response")
    return bool(answer and answer.get("caught"))


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
        # Mandatory per move (book), and a *required* field in the reference's
        # parser — omitting it made every one of our turns unreadable to it.
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if "barrier_placed" in payload:
        message["barrier_placed"] = payload["barrier_placed"]
    if payload.get("capture_claim"):
        # The claim IS the cell — that is the reference's shape, and it is the
        # better one: a bare `true` plus a separate `claimed_cell` field made
        # the message unparseable by a reference peer, whose parser rejects any
        # field it does not declare. Claiming still discloses where we stand,
        # which is what stops a cop claiming speculatively every turn.
        message["capture_claim"] = list(payload["capture_claim"])
    if payload.get("claim_response") is not None:
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
