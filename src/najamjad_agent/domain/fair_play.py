"""Watching the opponent for rule violations, across a whole series.

Commit-reveal already stops an opponent *rewriting* history: every turn is
sealed and the audit catches an altered record (book rules 18-22). What nothing
watched is an opponent who never lies about what they did, but does something
the rules do not allow — and that gap is not hypothetical. Replaying a real
series turned up a peer whose cop moved to a new cell **and** declared a barrier
on the same turn, fourteen times. The book is explicit (FR-ENG-3, Barrier Law):
a barrier is placed *in lieu of moving*. Fourteen free actions is a large edge,
and nothing in our agent would have noticed.

Design choices worth stating:

* **Observe, never retaliate.** A violation is recorded with its evidence and
  surfaced; it never changes our play and never forfeits their game. Deciding a
  match on our own accusation is exactly the contradiction rules 33-35 void both
  teams for, and an honest peer with an off-by-one bug is far more likely than a
  cheat.
* **Evidence, not verdicts.** Each finding carries the step and the two facts
  that conflict, so a human can settle it with the opponent in one message.
* **Silence is a finding too.** A clean series is worth recording, because
  "we checked and found nothing" is the sentence that makes the report credible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .board import Board
from .params import Position


@dataclass(frozen=True)
class Violation:
    """One rule breach, with enough context to raise it with the opponent."""

    step: int
    rule: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        """The shape the report and the event log carry."""
        return {"step": self.step, "rule": self.rule, "detail": self.detail}


@dataclass
class FairPlayMonitor:
    """Accumulates rule breaches observed in the opponent's declared turns."""

    max_barriers: int
    #: Defaults to the Appendix F term rather than being required, because
    #: `GameParams` does not carry it — it lives in `game.json` under `world`,
    #: and `hint_guard` hardcodes the same 15. One place to change if a match
    #: ever negotiates a different cap.
    hint_max_words: int = 15
    findings: list[Violation] = field(default_factory=list)
    barriers_seen: int = 0
    _last_cell: Position | None = None
    _last_step: int = 0

    @property
    def clean(self) -> bool:
        """True when nothing questionable has been observed."""
        return not self.findings

    def _flag(self, step: int, rule: str, detail: str) -> None:
        self.findings.append(Violation(step, rule, detail))

    def observe(self, board: Board, step: int, message: dict[str, Any]) -> list[Violation]:
        """Check one declared opponent turn; return anything new it raised.

        Input: the board as we hold it, the step number, and their raw message.
        Output: the violations this turn added (empty for an honest turn).
        Setup: none — pure, so a replayed log audits identically offline.
        """
        before = len(self.findings)
        cell = _cell(message.get("position") or message.get("cell"))
        barrier = _cell(message.get("barrier_placed"))
        self._check_step_order(step)
        self._check_move(board, step, cell)
        self._check_barrier(board, step, barrier, cell)
        self._check_hint(step, message.get("hint"))
        if cell is not None:
            self._last_cell = cell
        self._last_step = step
        return self.findings[before:]

    def _check_step_order(self, step: int) -> None:
        """Steps advance by one; a jump hides a turn nobody can audit."""
        if self._last_step and step != self._last_step + 1:
            self._flag(step, "step-order", f"step {step} follows {self._last_step}")

    def _check_move(self, board: Board, step: int, cell: Position | None) -> None:
        """A declared position must be reachable from the last one."""
        if cell is None:
            return
        if not board.in_bounds(cell):
            self._flag(step, "off-board", f"declared {list(cell)}")
            return
        if board.is_blocked(cell):
            self._flag(step, "through-barrier", f"declared {list(cell)}, which is walled")
        if self._last_cell is not None:
            hop = Board.manhattan(self._last_cell, cell)
            if hop > 1:
                self._flag(
                    step,
                    "teleport",
                    f"{list(self._last_cell)} -> {list(cell)} is {hop} steps in one turn",
                )

    def _check_barrier(
        self, board: Board, step: int, barrier: Position | None, cell: Position | None
    ) -> None:
        """The Barrier Law: cop-only, budgeted, in reach, and instead of moving."""
        if barrier is None:
            return
        self.barriers_seen += 1
        if self.barriers_seen > self.max_barriers:
            self._flag(
                step, "barrier-budget", f"barrier {self.barriers_seen} of an agreed {self.max_barriers}"
            )
        if not board.in_bounds(barrier):
            self._flag(step, "barrier-off-board", f"declared {list(barrier)}")
            return
        previous = self._last_cell
        if cell is not None and previous is not None and cell != previous:
            self._flag(
                step,
                "barrier-and-move",
                f"moved {list(previous)} -> {list(cell)} and walled "
                f"{list(barrier)} on one turn; the Barrier Law is in lieu of moving",
            )
        if cell is not None and Board.manhattan(cell, barrier) > 1:
            self._flag(
                step,
                "barrier-out-of-reach",
                f"walled {list(barrier)} from {list(cell)}, "
                f"{Board.manhattan(cell, barrier)} steps away",
            )

    def _check_hint(self, step: int, hint: Any) -> None:
        """The word cap is an agreed term, so exceeding it is a breach not a style."""
        words = len(str(hint or "").split())
        if words > self.hint_max_words:
            self._flag(step, "hint-length", f"{words} words against an agreed {self.hint_max_words}")

    def summary(self) -> dict[str, Any]:
        """What the match report carries — findings, or an explicit all-clear."""
        return {
            "clean": self.clean,
            "violations": [finding.as_dict() for finding in self.findings],
            "rules_broken": sorted({finding.rule for finding in self.findings}),
        }


def _cell(raw: Any) -> Position | None:
    """Read a coordinate pair defensively; peers send what they like."""
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None
