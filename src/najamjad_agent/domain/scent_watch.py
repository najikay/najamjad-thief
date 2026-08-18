"""Did the opponent actually transmit a trail, and did it point at themselves.

Two questions our logs could not answer for three separate opponents, which is
how a counted series was lost and then mis-diagnosed twice in one day. Both are
cheap to answer per mini-game and neither needs anything the peer volunteers.

* **silence** — how many inbound turns carried a populated `smell_grid`. A peer
  that sends none is playing a different information game from us, and it is our
  standing term (terms document §4) that both sides transmit. It is legal under
  the book, which forbids faking a trail rather than withholding one, so this
  reports rather than forfeits: an operator can stop a friendly, and a counted
  series is worth finishing and disputing on the record instead of abandoning.
* **honesty** — whether the peak cell of each frame matches the position they
  reveal for that step at the audit. *That* is the rule the book actually sets,
  and a mismatch is a rule-23 finding with the evidence attached.

Both are computed from data we already keep: the frames recorded on ingress and
the records revealed at the audit. Nothing new is asked of the peer.
"""

from typing import Any

#: Inbound turns to see before judging silence. One quiet frame is a peer
#: starting up; five is a policy.
GRACE = 5


def silence(frames: Any) -> dict[str, Any]:
    """How much of what arrived carried a trail at all."""
    seen = list(getattr(frames, "all", lambda: [])() or [])
    grids = [f for f in seen if getattr(f, "grid", None)]
    return {
        "turns": len(seen),
        "with_scent": len(grids),
        "silent": len(seen) >= GRACE and not grids,
    }


def dishonest_steps(frames: Any, revealed: dict[int, tuple[int, int]]) -> list[dict[str, Any]]:
    """Steps where their declared peak is not the cell they later revealed.

    Only steps we hold both halves for are judged. A tie inside their field can
    move the peak to a neighbour without anyone lying, so a single mismatch is
    evidence to look at rather than a verdict — the pattern is what matters, and
    against nis-yar1 the honest answer was 36 of 36 exact.
    """
    out = []
    for frame in getattr(frames, "all", lambda: [])() or []:
        grid = getattr(frame, "grid", None) or {}
        step = getattr(frame, "step", None)
        if not grid or step not in revealed:
            continue
        numeric = {k: v for k, v in grid.items() if isinstance(v, int | float)}
        if not numeric:
            continue
        top = max(numeric, key=lambda k: numeric[k])
        peak = tuple(int(part) for part in str(top).split(",")) if isinstance(top, str) else tuple(top)
        if peak != revealed[step]:
            out.append({"step": step, "declared_peak": list(peak), "revealed": list(revealed[step])})
    return out
