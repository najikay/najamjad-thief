"""The thief's move policy — survive 35 steps, don't merely run.

The win condition shapes everything: the thief does not need to escape, only to
last. That makes greedy distance-maximisation a trap, because the move that puts
the most cells between us and the cop is very often the one that backs us into a
corner where a single barrier ends the game.

So a move is scored on three things at once:

* **Distance** under our belief about where the cop is;
* **Room** — escape routes and reachable freedom, which is what the cop's
  barriers are actually attacking;
* **Scent** — we cannot fake our trail (book PAGE 22), but we can avoid
  re-walking ground we have already perfumed, which is the only way to keep our
  emitted evidence from pointing straight at us.

A two-ply lookahead asks what the cop can do next, so we avoid moves that look
safe now and are lost a turn later.

**That is the policy for a cop we can locate, and only that.** All three terms
above are statements about where the opponent is, so all three are meaningless
when the belief does not name a cell — and against a peer who transmits nothing
at all, it never does. Feeding them a flat distribution anyway is what cost us
three archived mini-games: see `_blind_move`, which owns that case now, and
`strategy/blind.py` for what can still be proven when nobody tells us anything.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from ..constants import Move
from ..domain.board import Board
from ..domain.params import Position
from . import blind, solver, thief_safety, wall_safety
from .base import apply, confident_peak, expected_distance
from .thief_escape import corridor_risk, escape_routes, trap_penalty

#: How many times the uniform share the peak must hold before we call the
#: belief a localisation. Four is comfortably below what a real scent fix
#: produces (the freshest deposit clamps at the ceiling while the rest decay)
#: and comfortably above a flat prior, which is what step 1 looks like.
DISTANCE_WEIGHT = 1.0
ROOM_WEIGHT = 0.9
SCENT_WEIGHT = 0.6
RISK_WEIGHT = 2.5
# One ply of cop response. Deeper search buys little on a 7x7 board and costs
# time we owe the 30 s turn budget.
LOOKAHEAD = 1


@dataclass
class ThiefBrain:
    """Deterministic evasion policy for the thief role."""

    board_supplier: Any = None
    horizon: int = 3
    #: How many steps from the survival horizon the policy switches to stalling.
    #: Surviving to step 35 and surviving to step 100 score the same, so the last
    #: turns are a different game: a move that is safe *now* beats one that is
    #: better positioned for a future that will not arrive. Three, because a
    #: corridor takes two moves to escape and one to enter.
    stall_trigger: int = 3
    #: How much the endgame weights room over distance. High enough to dominate
    #: position, not so high that the thief walks toward the cop to find space.
    stall_room_weight: float = 4.0

    def steps_remaining(self, facts: Any) -> int:
        """Turns left before survival, or a large number when nobody says.

        Most callers do not supply a countdown, and a thief that assumed the
        endgame by default would spend thirty steps hugging open ground instead
        of getting away.
        """
        left = getattr(facts, "steps_remaining", None)
        return int(left) if isinstance(left, int) else self.stall_trigger + 1

    def is_endgame(self, facts: Any) -> bool:
        """Whether the horizon is close enough to stop taking chances."""
        return self.steps_remaining(facts) <= self.stall_trigger

    def pick_move(self, facts: Any) -> Move:
        """Choose the move that best preserves survival, not just distance.

        The safety rule owns this decision whenever we know where the cop is,
        which — given the pheromone field's freshest deposit is always its
        unique maximum — is every turn against an opponent who transmits one.
        The old weighted sum survives only as the fallback for a peer who sends
        nothing, and it is a fallback because it lost three games as a policy.
        """
        board: Board = self._board(facts)
        legal = tuple(getattr(facts, "legal", ()) or ())
        if not legal:
            return Move.STAY
        belief = dict(getattr(facts, "belief", {}) or {})
        origin: Position = getattr(facts, "own_position", (0, 0))
        cop = self._cop_cell(belief)
        if cop is not None:
            # No `barriers_left` argument: `facts.barriers_left` is *our* quota,
            # and a thief's is always zero, so passing it disabled the cut-cell
            # guard for the only role that needs it. The board carries the
            # cop's true remaining count.
            # **The solve filters the candidates, not the winners.** It used
            # to run over `tied` — the moves the heuristics had already called
            # equal-best — so a move that is provably lost but *uniquely*
            # top-ranked never reached it, and `or tied` then played it. That
            # is not a tie-break, it is the difference between playing well and
            # playing correctly, and it is exactly how a sealing cop takes us:
            # the heuristics like a cell for its room while the solve knows the
            # cop can force a capture from it.
            #
            # Filtering first costs nothing when nothing is losing, which on an
            # intact grid is always. Falling back to the whole legal set when
            # *everything* loses is deliberate: a lost position is where an
            # imperfect opponent might still err, and refusing to move is not
            # available to us.
            options = self._provably_safe_moves(board, origin, cop, legal) or legal
            tied = thief_safety.choose(board, origin, cop, options)
            return self._break_tie(tied, facts)
        open_cells = sum(1 for cell in board.cells() if board.is_open(cell))
        if blind.uninformative(belief, open_cells):
            # A belief spread across most of the board cannot name a *direction*
            # either, so the weighted sum below is not merely uninformed here —
            # it is actively misled. `_blind_move` is the honest policy.
            #
            # Asked of the belief's *support*, not of `located`. A five-cell
            # localisation is far too broad to name a cell and far too sharp to
            # throw away, and routing it here on the strength of `_cop_cell`
            # saying no cost two self-play games at blur 1.
            return self._blind_move(board, origin, legal, facts)
        # Our own trail, not theirs. `facts.scent` is the *opponent's* field,
        # and the leak term asks where **we** have already been — a different
        # question, and one that was being answered with the wrong agent's data
        # for as long as this policy has existed.
        return self._weighted_move(board, origin, legal, belief, facts)

    def _weighted_move(
        self,
        board: Board,
        origin: Position,
        legal: tuple[Move, ...],
        belief: dict[Position, float],
        facts: Any,
    ) -> Move:
        """The weighted-sum objective: our fallback, and our reduced-strength play.

        `facts.scent` is the *opponent's* field; the leak term asks where **we**
        have already been, so it reads `own_scent` — a different question, and
        one this policy answered with the wrong agent's data for as long as it
        existed.
        """
        scent = dict(getattr(facts, "own_scent", {}) or {})
        endgame = self.is_endgame(facts)
        return max(
            legal,
            key=lambda move: (
                self._value(board, origin, move, belief, scent, endgame),
                move.value,
            ),
        )

    def _blind_move(self, board: Board, origin: Position, legal: tuple[Move, ...], facts: Any) -> Move:
        """Hand the decision to `strategy/blind.py`, keeping our tie-break.

        The tie-break stays here because it is the *same* seeded digest the
        informed path uses: variation across sub-games, never within a replay,
        so the audit can reproduce any game byte for byte.
        """
        return blind.choose(
            board,
            origin,
            legal,
            int(getattr(facts, "step", 0)),
            lambda shortlist: self._break_tie(shortlist, facts),
        )

    def _provably_safe(
        self, board: Board, origin: Position, cop: Position, tied: tuple[Move, ...]
    ) -> tuple[Move, ...]:
        """Narrow a shortlist to the moves the exact solve says cannot lose.

        This is the difference between playing well and playing correctly. The
        heuristics above rank moves; `solver` *computes* which positions the cop
        can force a capture from, by backward induction over all 4802
        perfect-information states, and a thief that never enters one cannot be
        caught by pursuit at all.

        Applied as a filter over the heuristic shortlist rather than instead of
        it, because the two answer different questions and both are needed. The
        solve models a cop that only *moves*, so it is exact against pursuit and
        silent about walls — it is re-run whenever a barrier lands, but it
        cannot anticipate the next one. The heuristics are what keep us out of
        the pockets a barrier would seal. Filter first, rank within.

        Empty means every shortlisted move loses to perfect play, which on an
        intact grid cannot happen; the caller then keeps the heuristic order,
        since a lost position is exactly where an imperfect opponent might
        still err.
        """
        safe = set(self._safe_landings(board, cop, origin))
        return tuple(move for move in tied if apply(board, origin, move) in safe)

    def _safe_landings(self, board: Board, cop: Position, origin: Position) -> tuple[Position, ...]:
        """Landings that survive the chase *and* the cop's next barrier.

        `solver` has no barrier moves, so it calls a landing safe that one wall
        turns into a forced capture. Against a cop holding fourteen of them that
        is not safety, and it is the likeliest reason this thief was caught at
        step 13 in three consecutive counted mini-games while knowing the cop's
        exact cell the whole time.
        """
        moves = solver.safe_landings(board, cop, origin)
        left = int(getattr(self, "_their_barriers_left", 14) or 0)
        tightened = wall_safety.safe_landings(board, cop, origin, left, moves)
        # Never return empty when the loose oracle had something: a position
        # that loses to a perfect waller may still be held against a real one,
        # and an empty shortlist would drop us into the blind fallback.
        return tightened or moves

    def _provably_safe_moves(
        self, board: Board, origin: Position, cop: Position, legal: tuple[Move, ...]
    ) -> tuple[Move, ...]:
        """The legal moves that do not hand the cop a forced capture.

        The same filter as `_provably_safe`, applied to the candidates before
        they are ranked rather than to the ranking's winners. Kept as its own
        method because the two are asked at different moments and only this one
        is allowed to be empty.
        """
        return self._provably_safe(board, origin, cop, legal)

    def _cop_cell(self, belief: dict[Position, float]) -> Position | None:
        """The cop's cell when the belief actually names one, else None.

        The confidence check is the point. Taking `max()` of a *flat*
        distribution returns an arbitrary cell and reports it as certain, which
        is the confidently-wrong failure the whole safety rule exists to avoid —
        and it is not hypothetical. On step 1 no scent has arrived yet, the
        belief is uniform, and a re-baseline caught this thief striding
        confidently into a cop two cells away and being taken on the first move.

        A real localisation is sharply peaked: our scent field clamps the
        freshest deposit at the ceiling while everything older decays, so the
        true cell carries far more mass than an even share. Requiring several
        times the uniform share separates "I know" from "I have no idea",
        and when we have no idea the diffuse-belief policy below is the honest
        answer.
        """
        return confident_peak(belief)

    def _break_tie(self, tied: tuple[Move, ...], facts: Any) -> Move:
        """Pick among equally safe moves, unpredictably but never unsafely.

        Randomising *only* within the tied set is the whole discipline. A
        scripted opponent solved our previous thief by replaying one line
        against it three times, so playing the same game twice is a real cost —
        but so is trading a safe move for a varied one, and this trades none.

        Seeded from the sub-game so a match stays reproducible for the audit:
        the same game replays identically, different games do not.

        **`hash()` was the wrong function.** On a tuple of two small integers
        CPython's hash is very nearly linear, so consecutive sub-games mapped to
        the same residue again and again: across six sub-games and four tied
        moves it produced three distinct choices at step 1 and *two* at steps 2
        and 3. The archive shows the consequence — our g04 and g06 lines came out
        byte-identical, which is precisely the property a scripted opponent
        solved us for. A digest costs a microsecond and spreads properly.

        Still fully deterministic: BLAKE2b of the same seed is the same byte on
        every machine and every replay, which `hash()` guarantees for ints but
        not for anything else we might key on later.
        """
        if len(tied) == 1:
            return tied[0]
        sub_game = int(getattr(facts, "sub_game", 1))
        step = int(getattr(facts, "step", 0))
        seed = hashlib.blake2b(f"{sub_game}:{step}".encode(), digest_size=8).digest()
        index = int.from_bytes(seed, "big") % len(tied)
        return sorted(tied, key=lambda move: move.value)[index]

    def pick_barrier(self, facts: Any) -> Position | None:
        """Thieves never place barriers (cop-only power, book Ch. 3)."""
        return None

    def _value(
        self,
        board: Board,
        origin: Position,
        move: Move,
        belief: dict[Position, float],
        scent: dict[Position, float],
        endgame: bool = False,
    ) -> float:
        """Higher is better: distance and room, minus risk and self-betrayal.

        In the endgame the weights change rather than the shape: room is worth
        several times more and raw distance almost nothing, because a cell we
        cannot be trapped in for two turns wins a game that a cell three steps
        further away does not.

        **Only reached with a belief that names a cell.** Both distance terms
        are meaningless otherwise — see `_blind_move`, which is where a flat
        belief goes now — and calling this with one is how the thief spent three
        archived games standing still.
        """
        landing = apply(board, origin, move)
        if not board.is_open(landing):
            return float("-inf")
        distance = expected_distance(belief, landing) if belief else 0.0
        room = escape_routes(board, landing)
        risk = corridor_risk(board, landing, self.horizon) + trap_penalty(board, landing)
        leak = scent.get(landing, 0.0)
        worst_next = self._worst_case(board, landing, belief)
        if endgame:
            # Room dominates and distance nearly vanishes: with a step or two
            # left, a cell we cannot be trapped in wins the game that a cell
            # three squares further away does not. Risk keeps its full weight —
            # the point is to stop gambling, not to stop looking.
            return (
                self.stall_room_weight * room
                - RISK_WEIGHT * risk
                - SCENT_WEIGHT * leak
                + DISTANCE_WEIGHT * worst_next
            )
        return (
            DISTANCE_WEIGHT * distance
            + ROOM_WEIGHT * room
            - RISK_WEIGHT * risk
            - SCENT_WEIGHT * leak
            + DISTANCE_WEIGHT * worst_next
        )

    def _worst_case(self, board: Board, landing: Position, belief: dict[Position, float]) -> float:
        """Distance we would still hold after the cop's best reply.

        Without this, a move that maximises distance now but hands the cop a
        free cut-off looks identical to one that keeps us genuinely clear.
        """
        if not belief:
            return 0.0
        threat = max(belief, key=lambda cell: belief[cell])
        approaches = board.neighbours(threat) or (threat,)
        return min(Board.manhattan(landing, approach) for approach in approaches)

    def _board(self, facts: Any) -> Board:
        """The board to reason over, supplied by the orchestrator or the facts."""
        if self.board_supplier is not None:
            return self.board_supplier()
        return facts.board
