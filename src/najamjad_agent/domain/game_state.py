"""Mutable per-mini-game state, owned exclusively by the orchestrator.

Kept separate from the orchestrator so a mini-game can be reset, snapshotted for
crash-resume, and inspected by the dashboard without touching the conductor's
logic.
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import EndReason, Move, Role
from .belief import BeliefGrid
from .board import Board
from .emission import EmissionPolicy
from .hint_evidence import CredibilityTracker
from .ledger import CommitLedger
from .params import Position
from .scent import ScentField
from .scent_audit import FrameLog


@dataclass
class TurnFacts:
    """The read-only view handed to a brain or speaker for one decision."""

    step: int
    role: str
    own_position: Position
    legal: tuple[Move, ...]
    belief_peak: Position | None
    belief: dict[Position, float]
    #: The **opponent's** trail — the field our belief is inferred from.
    scent: dict[Position, float]
    #: **Our own** trail, which is a different field answering a different
    #: question: not "where are they" but "where have I already told them I
    #: was". `thief_brain._value` asks the second and was handed the first, so
    #: the term meant to stop us re-treading perfumed ground was reading the
    #: opponent's deposits instead — and was identically zero against a peer
    #: that emits nothing.
    own_scent: dict[Position, float] = field(default_factory=dict)
    last_hint: str = ""
    barriers_left: int = 0
    #: Which mini-game this decision belongs to. The speaker reads it to bill
    #: the LLM call, and without it every token in a six-game series was
    #: recorded against sub-game 0 — so the meter held ~7,300 tokens while the
    #: emitted report said each game cost nothing and the series total was 0.
    sub_game: int = 0


@dataclass
class GameState:
    """Everything one peer knows during a single mini-game."""

    board: Board
    role: Role
    sub_game: int
    own_position: Position
    belief: BeliefGrid
    own_scent: ScentField
    opponent_scent: ScentField
    ledger: CommitLedger
    step: int = 0
    full_turns: int = 0
    last_opponent_hint: str = ""
    opponent_estimate: Position | None = None
    pending_capture_claim: bool | None = None
    claimed_cell: Position | None = None
    # Position evidence read out of the opponent's *mandatory* declarations — a
    # capture claim or a barrier (see `domain/cop_sighting.py`). Held here rather
    # than applied at absorb time because it has to be fused in the right order:
    # after the diffusion step that models their move, alongside the scent, or a
    # point observation gets blurred across five cells before anything reads it.
    #
    # `last_sighting` outlives it, because plausibility is judged against the
    # previous sighting and a peer that stops declaring must not reset that.
    cop_sighting: Any = None
    last_sighting: Any = None
    #: The opponent's transmitted grids, kept for the length of this mini-game
    #: and read once at the audit, when their revealed positions finally make
    #: the comparison possible. See `domain/scent_audit.py`.
    opponent_frames: Any = field(default_factory=FrameLog)
    # How much this opponent's words have been worth so far. Lives on the
    # state rather than in `hint_evidence` so it accumulates across the
    # whole mini-game: a peer caught lying once is discounted for the rest
    # of it, and one telling the truth earns weight it did not start with.
    credibility: CredibilityTracker = field(default_factory=CredibilityTracker)
    # How much of our own evidence we disclose each turn (`domain/emission.py`).
    # Defaulted rather than required so every existing construction keeps the
    # behaviour it had: full scent, hints spoken.
    emission: EmissionPolicy = field(default_factory=EmissionPolicy)
    # Consecutive opponent turns carrying neither scent nor a hint. Feeds
    # `EmissionPolicy.mirroring`, so we only ever go quiet after watching
    # them do it first — reciprocity has to be reciprocal to be worth the name.
    peer_silent_turns: int = 0
    # An ending we have detected but not yet told the opponent about. Both peers
    # must record the same reason or rules 33-35 void the game, and they cannot
    # detect every ending at the same moment: the turn order means one side sees
    # it a half-turn earlier. So the side that sees it first announces it on one
    # final sealed turn, and only then closes the game.
    pending_end: EndReason | None = None
    barriers_used: int = 0
    # Watches the opponent's declared turns for rule breaches commit-reveal
    # cannot see — an opponent who reports truthfully but plays something the
    # rules disallow. Optional so every existing construction still works, and
    # observational only: it records, it never changes our play.
    fair_play: Any = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def barriers_left(self) -> int:
        """Remaining barrier quota for the cop (Appendix F Table 15)."""
        return self.board.params.max_barriers - self.barriers_used

    def facts(self, legal: tuple[Move, ...]) -> TurnFacts:
        """Snapshot the decision inputs for this turn."""
        return TurnFacts(
            sub_game=self.sub_game,
            step=self.step,
            role=self.role.value,
            own_position=self.own_position,
            legal=legal,
            belief_peak=self.belief.peak(),
            belief=self.belief.as_dict(),
            scent={
                cell: self.opponent_scent.intensity_at(cell) for cell in self.board.cells()
            },
            own_scent={cell: self.own_scent.intensity_at(cell) for cell in self.board.cells()},
            last_hint=self.last_opponent_hint,
            barriers_left=self.barriers_left,
        )

    def snapshot(self) -> dict[str, Any]:
        """Serialisable state for crash-resume and the dashboard."""
        return {
            "sub_game": self.sub_game,
            "role": self.role.value,
            "step": self.step,
            "full_turns": self.full_turns,
            "own_position": list(self.own_position),
            "barriers_used": self.barriers_used,
            "barriers": sorted([row, col] for row, col in self.board.barriers),
            "belief_peak": list(self.belief.peak() or ()),
            "opponent_scent": self.opponent_scent.snapshot(),
            "last_opponent_hint": self.last_opponent_hint,
        }

    def state_string(self) -> str:
        """Compact state description sealed into each commit record."""
        barriers = sorted([row, col] for row, col in self.board.barriers)
        size = self.board.size
        return f"grid={size}x{size};self={list(self.own_position)};barriers={barriers}"
