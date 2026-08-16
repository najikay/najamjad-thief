"""Reading the opponent's position out of the things the rules force them to say.

Our belief engine was built around one evidence channel — the pheromone field —
and against an opponent who emits one it is excellent. Against uoh-sqak it was
worthless, because they emit nothing at all: no scent, no hints, zero
observations. The belief stayed uniform for the whole mini-game, the confidence
check in `thief_brain._cop_cell` correctly refused to name a cell from a flat
distribution, and the thief fell back to the weighted-sum policy that had
already lost three games. It sat at (5,4) for twenty-five turns, and once they
fixed their own claim-on-STAY bug it was captured at turn 10, three times out
of three.

But they are not actually silent. The rules make two things public, and both
are position-bearing:

* **A capture claim** (rules 21-22). The claim must name a cell, because a thief
  who cannot see the cop could not answer honestly otherwise — and every
  implementation in this league fills that field with the cop's *own* position,
  on every move it makes rather than only when it lands. That is measured, not
  assumed: see `from_claim`. So a claim is the cop's exact cell, mandatory, and
  free to us. There were 146 of them in one series.
* **A barrier declaration** (rules 15-16, FR-ENG-3). The Barrier Law is *in lieu
  of moving*, on the cop's own cell or one orthogonally adjacent to it. So a
  declared barrier puts the cop in a five-cell set and says it did not move that
  turn. There were 143 of those.

Two hundred and eighty-nine position disclosures per series, and we were
throwing every one of them away.

**Why these are modelled differently.** A claim is a point observation and is
treated as near-certain: lying about it is provable at the audit, and a cop that
claims a cell it is not standing on has forfeited the game it is trying to win.
A barrier is a *set* and is treated as soft evidence, because the reach rule
admits five cells and we cannot tell which — and because an opponent whose
barrier logic differs from our reading of the rule should cost us a blurred
estimate, not a confidently wrong one.

Nothing here trusts a declaration that contradicts physics. A claim more than
one step from where we last placed the cop is either a bluff or a different game
than the one we think we are in, and `plausible` downgrades it to soft evidence
rather than believing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import Board
from .params import Position

#: Confidence attached to a capture claim: the cop named its own cell under a
#: rule that makes lying provable. Not 1.0 — `BeliefGrid` keeps a floor on every
#: other cell precisely so one mistaken observation is survivable, and a hard
#: 1.0 would be the only evidence in the system that cannot be recovered from.
CLAIM_CONFIDENCE = 0.99
#: Confidence attached to a barrier's five-cell reach set. High, because the
#: Barrier Law is not ambiguous, but not a claim: we are excluding 44 cells on
#: the strength of a rule the opponent implements themselves.
BARRIER_CONFIDENCE = 0.85
#: Confidence left to a declaration that fails the reachability check. Enough to
#: register that something happened, too little to move the peak on its own.
IMPLAUSIBLE_CONFIDENCE = 0.2


@dataclass(frozen=True)
class Sighting:
    """Where a public declaration says the opponent was, and how sure that is.

    `cells` is a *set*, not a point: a barrier names five candidates and a claim
    names one, and collapsing that distinction is how a five-way guess starts
    being reported as knowledge.
    """

    cells: tuple[Position, ...]
    confidence: float
    source: str
    step: int

    @property
    def exact(self) -> bool:
        """Whether this pins the opponent to a single cell."""
        return len(self.cells) == 1

    def as_event(self) -> dict[str, object]:
        """Log form, so a replay can see what the belief was told and when."""
        return {
            "source": self.source,
            "step": self.step,
            "cells": [list(cell) for cell in self.cells],
            "confidence": round(self.confidence, 3),
        }


def from_claim(cell: Position, step: int) -> Sighting:
    """A capture claim read as a position fix on the cop. **Wired, and measured.**

    This function was wired, removed, wired again and removed again, on the
    reading that a claim names the cell where the cop asserts *the thief* is
    rather than where the cop stands. The argument for that reading was
    `answer_capture_claim(true_thief_cell, claimed_cell)` — our own code compares
    the claim against the thief's position. That argument does not hold: the
    comparison is identical under both readings. A cop standing on X asking "are
    you on X?" is answered by exactly the same line as a cop guessing "I think
    you are on X". The receiver cannot distinguish them, so the receiver's code
    cannot settle which the sender meant.

    What settles it is the sender, and it was measurable all along:

    * **Both reference implementations** put the police's own position in the
      field — `turn_sender.py`: ``capture_claim = list(rt.state.position) if
      rt.role is Role.POLICE and decision.move_type is MoveType.MOVE`` — on
      every move, not only on a landing.
    * **Our own cop** does the same, deliberately, and `T-0535` locks it.
    * **323 of 323** capture claims in every sealed record in `matches/` name the
      claimer's own revealed position. Zero exceptions, across three agents; 306
      of them from uoh-ay26, an external opponent whose records we hold.

    So in this league the claim is the cop's exact cell, disclosed every turn it
    moves, and it is the single most precise position evidence the game emits.

    **Measured on the archived lines, replayed with their real declarations at
    the steps they were really declared on:** ignoring claims left the belief
    wrong by 2.04 cells on average, exact on 10% of turns, and **lost
    uoh-ay26/g03 to a capture at step 26**. Reading them put the belief on the
    cop's exact cell on **100%** of turns in both games and survived all 35.

    The harm the removals recorded was real and is now understood. It was a
    fusion interaction, not a semantic one: a claim naming *our own* cell put
    0.99 on our square, the next `exclude()` deleted it, and — the part that
    actually cost us — `_record_sighting`'s exact-beats-inexact rule had already
    let it evict the barrier sighting on the way past. `turn_ingress` drops a
    claim on our own cell before it is held, which restores the ignoring
    behaviour exactly (2.04 / 10% again, against 3.73 / 0% unguarded).

    What is *not* fixed, stated plainly: a peer that lies consistently — claiming
    a cell one row from where it stands, every turn — degrades us, and on the
    uoh-sqak sweep it turns 35/35 survival into a capture at step 14. No guard
    tried separates that peer from an honest one; `plausible` anchored on the
    signed `cop_start`, and refusing rather than downgrading an implausible
    claim, both failed under barrier cover, and widening the own-cell guard to
    the surrounding ring was strictly worse (it re-lost g03 while holding a
    near-perfect belief, by discarding the claim exactly when the cop was
    adjacent). We take that exposure because it requires an opponent to lie about
    its own position on the wire, which has never been observed, and because
    `scent_audit` now checks every claim against their revealed records so a peer
    that does it leaves the evidence in our archive.
    """
    return Sighting((cell,), CLAIM_CONFIDENCE, "capture_claim", step)


def from_barrier(board: Board, cell: Position, step: int) -> Sighting | None:
    """A barrier declaration: the cop is on `cell` or one step from it.

    Input: the board *after* the barrier has landed, the walled cell, the step.
    Output: a soft sighting over the reach set, or None when it names nothing.

    The walled cell itself is dropped when the board says it is closed, which is
    the normal case — the belief grid only tracks open cells, and a cop that
    walled the ground under its own feet has immobilised itself permanently and
    stopped being a threat worth modelling.
    """
    reach = [cell, *board.neighbours(cell)]
    candidates = tuple(sorted({spot for spot in reach if board.is_open(spot)}))
    if not candidates:
        return None
    return Sighting(candidates, BARRIER_CONFIDENCE, "barrier", step)


def plausible(sighting: Sighting, previous: Sighting | None, elapsed: int = 1) -> Sighting:
    """Downgrade a sighting that could not have followed the one before it.

    An opponent moves at most one cell per turn, so a claim eight squares from
    the last confirmed sighting is not evidence, it is a bluff or a desync. We
    do not refuse it — refusing would let an opponent freeze our belief simply by
    declaring nonsense — but we stop letting it overwrite what we know.

    `elapsed` is how many turns passed, so a sighting after a quiet stretch is
    held to a proportionally looser bound rather than being rejected for the
    crime of being late.
    """
    if previous is None:
        return sighting
    budget = max(1, elapsed) + (0 if previous.exact else 1)
    if any(
        Board.manhattan(cell, earlier) <= budget
        for cell in sighting.cells
        for earlier in previous.cells
    ):
        return sighting
    return Sighting(
        sighting.cells, IMPLAUSIBLE_CONFIDENCE, f"{sighting.source}:implausible", sighting.step
    )
