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

* **A capture claim** (rules 21-22). A capture requires the cop to *be* on the
  thief's cell and say so — `domain/capture.evaluate_capture` will not score one
  otherwise — and the claim must name the cell, because a thief who cannot see
  the cop could not answer honestly if it did not. So a claim is the cop's exact
  cell, stated by the cop, mandatory, and free to us. There were 146 of them in
  one series.
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
    """A capture claim read as a position fix. **Deliberately never called.**

    This docstring used to say "the cop's exact cell", and that is wrong: a claim
    names the cell where the cop asserts **the thief** is. `answer_capture_claim(
    true_thief_cell, claimed_cell)` settles it from our own code — the claim is
    compared against the *thief's* position. It coincides with the cop's own cell
    only for a claim that lands, and uoh-sqak claiming only their own cell is the
    sole reason believing otherwise ever looked right.

    Wiring it in was measured and reverted **twice**. Against a cop claiming one
    row off, the thief went from surviving 35/35 to captured at step 13; against
    one claiming our own cell we were blinded every turn, because 0.99 of the
    mass landed on our own square and the next `exclude()` deleted it. Both are
    worse than ignoring claims outright.

    Kept rather than deleted because the shape is right and the *evidence* is
    real — it is the reading of it that is wrong, and a future session that
    deletes this will reach for it again. `test_a_capture_claim_is_not_treated_
    as_a_cop_position_fix` is the guard; read it before touching this.
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
