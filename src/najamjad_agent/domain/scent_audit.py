"""Check an opponent's transmitted trail against the positions they reveal.

Scent is the one channel the book calls unfakeable — an agent emits by existing
— but that is a property of an *honest* implementation, not of the wire. Nothing
stopped a peer from broadcasting a field centred somewhere it has never been,
and we had no way to notice: we absorbed every grid silently and kept only its
cell count.

imreeyal re-simulated all 105 of our transmitted grids from our audit-revealed
positions and reported them consistent to the last cell. We could not return the
favour, which is the wrong shape for a league where both sides check each other.

**The check is the argmax, not a re-simulation.** The centre of the freshest
deposit is the unique maximum of an honest field: under subtractive decay every
older cell has lost intensity, so the peak names where the emitter stood on the
step it sent. That makes this test independent of which snapshot a peer
transmits — teams in this league legitimately differ between the pre-decay 0.9
form and the post-decay 0.8 one, and a full re-simulation would have to know
which. The argmax is the same cell either way.

What it catches: a field centred on a decoy, a replayed trail, a grid that stops
tracking its emitter. What it does not catch: an honest field with a *scaled*
peak, and a peer who simply transmits nothing. Both are visible elsewhere —
`scent.absorbed` records the peak value and the cell count per frame.

**Their capture claims are checked the same way and for a sharper reason.** We
read a claim as a fix on the cop's own cell, which is sound only because every
implementation in this league fills that field with its own position — 323 of
323 sealed claims in `matches/` do. That is a measurement about opponents, not a
guarantee from the book, so it has to keep being measured. A peer that begins
naming a cell it is not standing on cannot do it invisibly: their own revealed
records convict them, one line per step, in our archive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .params import Position


@dataclass(frozen=True)
class TrailReport:
    """What their transmitted grids said about where they were."""

    checked: int = 0
    agreed: int = 0
    #: `(step, peak cells we were sent, the cell they revealed)`.
    mismatches: tuple[tuple[int, tuple[Position, ...], Position], ...] = ()
    #: Steps they revealed but sent no grid for. Not a fault — a silent peer is
    #: legal — but it is the difference between "verified" and "nothing to
    #: verify", and those must never read the same.
    unverifiable: int = 0
    #: The same comparison for their capture claims: `(step, claimed, revealed)`.
    #: We now read a claim as a fix on the cop's own cell (`cop_sighting.
    #: from_claim`), which is only sound while peers fill that field with their
    #: own position — 323 of 323 sealed claims in the archive do. This is how
    #: that stays a measurement instead of an assumption, and it is the reason
    #: the exposure is worth carrying: a peer that starts lying leaves it here.
    claim_mismatches: tuple[tuple[int, Position, Position], ...] = ()
    claims_checked: int = 0

    @property
    def clean(self) -> bool:
        """True when every frame we could check named the cell they revealed."""
        return not self.mismatches

    @property
    def claims_clean(self) -> bool:
        """True when every claim they made named the cell they later revealed."""
        return not self.claim_mismatches

    def as_event(self) -> dict[str, Any]:
        """The summary line for the event log."""
        return {
            "event": "scent.trail_verified" if self.clean else "scent.trail_mismatch",
            "checked": self.checked,
            "agreed": self.agreed,
            "unverifiable": self.unverifiable,
            "claims_checked": self.claims_checked,
            "claims_agreed": self.claims_checked - len(self.claim_mismatches),
            "claim_mismatches": [
                {"step": step, "they_claimed": list(claimed),
                 "they_revealed": list(revealed)}
                for step, claimed, revealed in self.claim_mismatches[:5]
            ],
            # Bounded: a peer whose every frame disagrees would otherwise write a
            # 35-entry structure into a line meant to be read at a glance.
            "mismatches": [
                {"step": step, "sent_peak": [list(cell) for cell in peaks],
                 "they_revealed": list(revealed)}
                for step, peaks, revealed in self.mismatches[:5]
            ],
        }


@dataclass
class FrameLog:
    """The opponent's grids as they arrived, keyed by the step that carried them.

    Held for the length of one mini-game and read once, at the audit, when their
    revealed records finally make the comparison possible. Storing the grid
    rather than a digest is deliberate: a digest proves a difference and names
    nothing, and the useful output here is *which cell* they claimed.
    """

    frames: dict[int, dict[str, float]] = field(default_factory=dict)
    #: The hint text that rode with each frame. Kept for the same reason as the
    #: grid and learned the same way: we judged a peer as sending no hints from
    #: their *revealed records*, and a build whose commit preimage omits the hint
    #: text structurally cannot carry one there — exactly as the league's default
    #: `smell_binding: none` puts no grid in a sealed record. The wire is the only
    #: place either claim can be settled, and we were not keeping it.
    hints: dict[int, str] = field(default_factory=dict)
    #: The cell each capture claim named, kept for the same reason and checked
    #: the same way. Recorded as sent, before anything reads it as evidence.
    claims: dict[int, Position] = field(default_factory=dict)

    def record(self, step: int, grid: dict[str, float], hint: str = "") -> None:
        """Keep one arriving frame. An empty grid is recorded as an empty grid."""
        self.frames[int(step)] = dict(grid or {})
        self.hints[int(step)] = str(hint or "")

    def record_claim(self, step: int, cell: Position) -> None:
        """Keep the cell one capture claim named."""
        self.claims[int(step)] = (int(cell[0]), int(cell[1]))

    def spoke(self) -> int:
        """How many steps carried a non-empty hint."""
        return sum(1 for text in self.hints.values() if text.strip())

    def clear(self) -> None:
        """Forget the mini-game just played."""
        self.frames.clear()
        self.hints.clear()
        self.claims.clear()


def peak_cell(grid: dict[str, float]) -> Position | None:
    """The single cell an honest field is centred on, or None when it names none.

    One argmax, shared by the audit and by both event lines. A second copy is how
    a replay ends up disagreeing with the audit that already ran and nobody can
    say which to believe — `replay/verifier.py`'s docstring makes the same point
    about hashing. Ties resolve to the lowest cell, deterministically, because an
    event log that reorders under a tie is not comparable across runs.
    """
    cells = _peak_cells(grid)
    return cells[0] if cells else None


def _peak_cells(grid: dict[str, float]) -> tuple[Position, ...]:
    """Every cell holding the maximum intensity, parsed to positions.

    A tuple rather than one cell because ties are possible and a tie is not a
    lie: a peer that has not moved re-deposits on its own cell, and rounding can
    put a neighbour level with it. The caller treats "revealed cell is among the
    peaks" as agreement.
    """
    numeric: dict[Position, float] = {}
    for key, value in grid.items():
        if not isinstance(value, int | float):
            continue
        parts = str(key).split(",")
        if len(parts) != 2:
            continue
        try:
            numeric[(int(parts[0]), int(parts[1]))] = float(value)
        except ValueError:
            continue
    if not numeric:
        return ()
    top = max(numeric.values())
    return tuple(sorted(cell for cell, value in numeric.items() if value == top))


def verify_trail(log: FrameLog, records: list[dict[str, Any]]) -> TrailReport:
    """Compare each grid they sent against the cell they later revealed.

    Input: the frames we kept during the mini-game, and their revealed records
        from the audit — each carrying `step` and `position`.
    Output: a `TrailReport`; never raises, because a malformed reveal is
        evidence about them and must not take our own settlement down with it.
    Setup: none.
    """
    revealed: dict[int, Position] = {}
    for record in records:
        payload = record.get("payload", record) if isinstance(record, dict) else {}
        cell = payload.get("position") if isinstance(payload, dict) else None
        if isinstance(cell, (list, tuple)) and len(cell) == 2:
            try:
                revealed[int(payload.get("step", -1))] = (int(cell[0]), int(cell[1]))
            except (TypeError, ValueError):
                continue

    checked = agreed = unverifiable = 0
    mismatches: list[tuple[int, tuple[Position, ...], Position]] = []
    claims_checked = 0
    claim_mismatches: list[tuple[int, Position, Position]] = []
    for step, cell in sorted(revealed.items()):
        claimed = log.claims.get(step)
        if claimed is not None:
            claims_checked += 1
            if claimed != cell:
                claim_mismatches.append((step, claimed, cell))
        grid = log.frames.get(step)
        peaks = _peak_cells(grid or {})
        if not peaks:
            unverifiable += 1
            continue
        checked += 1
        if cell in peaks:
            agreed += 1
        else:
            mismatches.append((step, peaks, cell))
    return TrailReport(
        checked, agreed, tuple(mismatches), unverifiable,
        tuple(claim_mismatches), claims_checked,
    )
