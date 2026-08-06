"""What the thief can still prove when the opponent transmits nothing.

uoh-sqak sent no scent, no hints and no observations for a whole series. Our
belief stayed flat, `thief_brain._cop_cell` correctly declined to name a cell
from it, and the fallback policy then had nothing to reason with — so it reasoned
with the flat belief anyway and invented a cop in the corner. Six mini-games of
near-total immobility followed.

The premise of this module is that "they told us nothing" is not the same as "we
know nothing". Two facts survive total silence, and neither depends on the
opponent's goodwill:

* **Where they started.** `cop_start` is a *negotiated term* in the agreement,
  fixed before the first move and identical in both configs. It is not a
  disclosure they can withhold.
* **How fast they can travel.** One cell per turn (FR-ENG-2). No exceptions —
  and a peer that broke this would be caught at the audit, when the sealed
  record is revealed and re-hashed.

Together those bound the cop inside a Manhattan ball of radius `step` around its
start. A cell outside that ball is one the cop **provably cannot occupy yet**,
and the margin is a number of turns of guaranteed warning.

**Why the warning saturates.** The obvious use — maximise the margin — is a
trap, and it is the same trap the phantom fell into: the cell furthest from the
cop's start is a corner, corners have two exits, and a thief that trades room
for distance is a thief one barrier from losing. Two turns of warning is enough
to react; a third buys nothing and costs the room that actually keeps us alive.
So the bonus is capped, and beyond the cap the room and trail terms decide.

The bound is *sound but perishable*. It goes vacuous once the ball covers the
board — about twelve steps from a corner on a 7x7 — and from then on this
contributes a constant and the rest of the policy carries the game. That is the
honest shape of the information: real early, gone later, never fabricated.
"""

from collections.abc import Callable

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from .base import apply
from .thief_escape import escape_routes, trap_penalty

#: Turns of guaranteed warning worth chasing. Two is a reaction, not a plan: it
#: is one turn to notice and one to move. Measured across 43 replayed sweeps,
#: raising it to three began trading room for distance and cost survivals.
WARNING_CAP = 2

#: Deliberately the same numbers the informed policy uses for room and traps.
#: Kept here rather than imported to avoid an import cycle, and stated as a
#: choice rather than a copy: both policies should value a square of open board
#: identically, because what a cell is worth spatially does not depend on
#: whether we currently know where the opponent is.
ROOM_WEIGHT = 0.9
TRAP_WEIGHT = 2.5

#: How far below the best score a move may sit and still be played. See
#: `choose` for why variation is bought at all, and at this price.
VARIATION_BAND = 1.0

#: How much a turn of warning is worth against a point of room. At 1.5 a
#: provably-safe cell outbids a neighbour with one extra exit, and does not
#: outbid a neighbour with two. Flat from 1.0 to 3.0 in measurement, so this is
#: the middle of a plateau rather than a fitted value.
WARNING_WEIGHT = 1.5


#: Share of the belief's mass that has to sit somewhere identifiable.
MASS_COVERED = 0.8

#: How much of the board may hold that mass before we call the belief useless.
#: Half is deliberately generous — this decides only whether the *distance*
#: terms are allowed to speak, and a belief covering a third of a 7x7 still
#: says something real about which way to run.
BLIND_SUPPORT = 0.5


def uninformative(belief: dict[Position, float], open_cells: int) -> bool:
    """True when no modest set of cells holds most of the belief's mass.

    Input: the belief, and how many cells of the board are open.
    Output: whether the distance terms should be silenced.

    **Not the same question as "can we name a cell", and conflating them was a
    regression.** `_cop_cell` refuses a 5-cell localisation because it cannot
    say *which* of the five — but five cells out of forty-nine is a great deal
    of information, and routing that to the blind policy threw it away. It cost
    two self-play games at blur 1 before the suite caught it.

    Measured by **support, not peak**. The obvious test — is the peak several
    times the uniform share — reports 1.00 for a belief spread evenly over five
    cells and 1.00 for one spread evenly over all forty-nine, because both are
    flat over whatever they cover. What separates them is how much of the board
    that is. Counting the cells needed to cover most of the mass handles the
    peaked case for free, since a sharp belief needs very few.
    """
    if not belief:
        return True
    total = sum(belief.values())
    if total <= 0:
        return True
    needed, seen = 0, 0.0
    for value in sorted(belief.values(), reverse=True):
        seen += value
        needed += 1
        if seen >= MASS_COVERED * total:
            break
    return needed > BLIND_SUPPORT * max(1, open_cells)


def earliest_arrival(board: Board, cell: Position, step: int) -> int:
    """Turns before the cop could *possibly* stand on `cell`, floored at zero.

    Input: the board (which carries the agreed `cop_start`), a cell, and the
    step about to be played.
    Output: a non-negative number of turns of guaranteed warning.
    Setup: none — pure arithmetic on the agreement, no opponent input at all.

    Zero means "they could already be here", which is the answer for most of the
    board after the opening. It is not a claim that they *are*.
    """
    return max(0, Board.manhattan(cell, board.params.cop_start) - step)


def warning_bonus(board: Board, cell: Position, step: int) -> float:
    """The saturated, weighted value of that warning, for a move score."""
    return WARNING_WEIGHT * min(earliest_arrival(board, cell, step), WARNING_CAP)


def score(board: Board, landing: Position, step: int) -> float:
    """Room, minus the trap penalty, plus whatever warning we can prove.

    Three terms the informed policy uses are deliberately absent, each because
    it was measured to *cost* survivals here rather than earn them:

    * **`corridor_risk`** — 20 survivals in 43 with it, 27 without. It scores a
      cell by how easily a cop could seal the corridor it sits in, which needs a
      cop whose position we know; blind, it only penalises the long open runs
      that are the safest ground on an empty board.
    * **our own trail** — 27 with, 36 without. It was added here to stop the
      thief standing still, and it does, but movement bought nothing: both
      variants died 0/20 to a cop that predicts us. Motion is not evasion when
      you are predictable, which is what `VARIATION_BAND` answers instead.
    * **the belief**, for the reasons in `choose`.
    """
    if not board.is_open(landing):
        return float("-inf")
    return (
        ROOM_WEIGHT * escape_routes(board, landing)
        - TRAP_WEIGHT * trap_penalty(board, landing)
        + warning_bonus(board, landing, step)
    )


def choose(
    board: Board,
    origin: Position,
    legal: tuple[Move, ...],
    step: int,
    tie_break: Callable[[tuple[Move, ...]], Move],
) -> Move:
    """Pick a move with no usable belief — the silent-opponent policy.

    Input: the board, where we stand, our legal moves, the step about to be
    played, and the caller's tie-break over a shortlist.
    Output: one move.
    Setup: none. Pure, and it asks the opponent for nothing.

    The belief is absent from this decision on purpose, and that is the whole
    correction. Under a flat distribution `expected_distance` measures board
    geometry rather than the opponent — a corner is on average further from
    every cell than the middle is — and the old `_worst_case` took `max()` of a
    flat dict, which returns whichever key CPython iterates first, always the
    cop's start. Between them they invented a cop in the corner and awarded the
    opposite corner for fleeing it. Measured from our own start against a silent
    peer: (3,3) to (6,5) in five steps, then STAY for the remaining thirty.

    **Why a near-best band and not the argmax.** On 70 held-out arenas, changing
    only which move wins a *tie* moved survival by fifteen games. That is the
    tell — against a fixed line, blind survival is mostly luck about which cell
    you park in, so squeezing that number is fitting noise. The threat we have
    actually measured is the other one: a scripted opponent solved our previous
    thief three times out of three by replaying one line, and within a series a
    peer watches five sub-games before the sixth. The band trades a survival we
    cannot rely on for variation we can — against an opponent that studied our
    first game, 32 survivals in 100 later games against 10 for the argmax, with
    held-out survival unchanged inside noise (43 against 44).

    None of this is a guarantee and it cannot be one. A silent opponent still
    reads *our* scent, so they see us while we do not see them, and no policy
    survives that asymmetry against every line.
    """
    if not legal:
        return Move.STAY
    scored = [(score(board, apply(board, origin, move), step), move) for move in legal]
    best = max(value for value, _ in scored)
    near = tuple(move for value, move in scored if value >= best - VARIATION_BAND)
    if len(near) > 1:
        return tie_break(near)
    # `near` always holds the argmax, so this is unreachable; stated rather than
    # indexed blindly because a shortlist that silently emptied would surface as
    # an IndexError inside a turn we still have to answer.
    return near[0] if near else legal[0]
