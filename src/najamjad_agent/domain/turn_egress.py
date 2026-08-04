"""Composing our own turn — the half of the protocol we are accountable for.

The mirror image of `turn_ingress`, and split from it because the two halves
answer opposite questions. Ingress asks "what may I believe from an untrusted
peer"; egress asks "what am I obliged to disclose, and what stays sealed".

The disclosure list is short and every item on it is there for a reason:

* the **scent field**, which is evidence we emit rather than a message we
  choose to send (book PAGE 22);
* a **hint**, free-language and permitted to be untrue;
* a **barrier**, which rules 15-16 require the placer to declare;
* a **capture claim**, which must name the cell it asserts;
* a **claim response**, which rules 21-22 require the thief to answer honestly.

Position, move and intent are *not* on it. They stay inside the commitment until
the audit, which is the trade the book makes: hidden information now, verifiable
honesty later.
"""

from datetime import UTC, datetime
from typing import Any

from .game_state import GameState


def outgoing_extras(state: GameState, barrier: Any, claim: Any = None) -> dict[str, Any]:
    """Optional sealed fields carried alongside our move.

    The scent snapshot is what the opponent absorbs; it deliberately contains
    intensities only, never a coordinate, so publishing it leaks evidence but
    not our position — although the argmax of a 5x5 deposit is its centre, so
    "not our position" is a statement about the message and not about what a
    competent reader can recover from it.

    How much of the field goes out is `state.emission`'s decision, applied here
    because here is *before* the payload is sealed. Trimming the wire message
    after the commit was computed would make our own commitment disagree with
    what we sent, which the audit reads as tampering (rules 18-22) — a
    forfeit-shaped way to save a few bytes.
    """
    extras: dict[str, Any] = {
        "smell_grid": state.emission.scent(state.own_scent.snapshot(), state.own_position)
    }
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
