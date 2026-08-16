"""Are we emitting scent on the same terms the opponent is? (T-2611)

    uv run python scripts/scent_parity.py
    uv run python scripts/scent_parity.py --events workspace/events.jsonl --since 2026-08-13T18:30

imreeyal re-simulated all 105 of our transmitted grids against our revealed
positions and told us they were consistent to the last cell. We could not return
the favour, and `scent_audit.verify_trail` was the answer to that half: it checks
*their* trail against *their* reveals.

This is the other half, and it asks a question neither tool does — not "is each
side honest" but "**are the two sides sending comparable things**". They are not
necessarily the same question, and the difference has already cost us:

* the handshake's `model_fingerprint` locks the emission *maths* (model, centre
  intensity, decay, grid size), so a matching fingerprint proves both sides
  compute the same field;
* it says nothing about **which snapshot of that field goes on the wire**. We
  transmit pre-decay (peak 0.9); imreeyal and vibecode transmit post-decay
  (peak 0.8). Two agreeing fingerprints, two trails that age at different rates
  in each other's belief — open item §5.2.

So the peak *value* is the tell, and the cell count is the other one: a peer
sending a 5x5 window and a peer sending the whole board are both legal and are
not the same disclosure. Both are read straight off the event log — `scent.emitted`
for us, `scent.absorbed` for them — so this compares two measurements rather
than a measurement against an assumption.

Observational. A difference here is a thing to *raise* with an opponent, not a
violation: the book forbids faking a trail, not choosing a snapshot.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_EVENTS = "workspace/events.jsonl"


def _rows(path: Path, since: str, until: str) -> list[dict]:
    """Event rows in the window, tolerating a partially written last line."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = str(row.get("ts", ""))
        if since <= stamp <= until:
            rows.append(row)
    return rows


def _summarise(rows: list[dict], event: str) -> dict | None:
    """Cells, peak and mode for one side's frames."""
    frames = [row for row in rows if row.get("event") == event]
    if not frames:
        return None
    cells = [int(row.get("cells", 0)) for row in frames]
    peaks = [float(row.get("peak", 0.0)) for row in frames]
    located = [row for row in frames if row.get("peak_cell")]
    return {
        "frames": len(frames),
        "cells_min": min(cells), "cells_max": max(cells),
        "cells_median": statistics.median(cells),
        "peaks": sorted({round(peak, 3) for peak in peaks}),
        "peak_median": round(statistics.median(peaks), 3),
        "modes": sorted({str(row.get("mode", "")) for row in frames if row.get("mode")}),
        "with_peak_cell": len(located),
        "silent_frames": sum(1 for count in cells if count == 0),
    }


def report(path: Path, since: str, until: str) -> int:
    """Print both sides' emission profile and what differs."""
    if not path.exists():
        print(f"no event log at {path}")
        return 1
    rows = _rows(path, since, until)
    ours = _summarise(rows, "scent.emitted")
    theirs = _summarise(rows, "scent.absorbed")

    print(f"event log: {path}  window: {since} .. {until}  ({len(rows)} events)")
    for label, side in (("we sent", ours), ("they sent", theirs)):
        if side is None:
            print(f"\n  {label}: no frames recorded")
            continue
        print(f"\n  {label}: {side['frames']} frames")
        print(f"    cells    min {side['cells_min']}  median {side['cells_median']}  "
              f"max {side['cells_max']}   ({side['silent_frames']} empty)")
        print(f"    peak     {side['peaks']}  median {side['peak_median']}")
        if side["modes"]:
            print(f"    mode     {', '.join(side['modes'])}")
        if label.startswith("they"):
            # Only their frames carry it. The centre of our own field is our own
            # cell, and logging that would publish the position commit-reveal
            # exists to seal — our own honesty is checkable from our own records.
            print(f"    frames carrying a peak cell: {side['with_peak_cell']} "
                  f"(needed to audit their honesty from the archive alone)")

    if ours is None:
        print("\n  ** Our own emission is not instrumented in this log. `scent.emitted`"
              "\n     landed after this match — replay a newer one to compare. **")
        return 0
    if theirs is None:
        print("\n  ** They emitted nothing we recorded. That is legal, and it is also"
              "\n     the asymmetry that lost the uoh-sqak series. **")
        return 0

    print("\n  difference")
    if ours["peak_median"] != theirs["peak_median"]:
        print(f"    PEAK: ours {ours['peak_median']} vs theirs {theirs['peak_median']}. "
              "A one-decay-step gap\n          is the pre-decay/post-decay convention "
              "(§5.2), not dishonesty — but it\n          means one trail ages twice in "
              "the other's field. Raise it with them.")
    else:
        print(f"    peak: both {ours['peak_median']} — same snapshot convention")
    if ours["cells_median"] != theirs["cells_median"]:
        print(f"    CELLS: ours {ours['cells_median']} vs theirs {theirs['cells_median']} "
              "(median). Both legal;\n           a wider field is a larger voluntary "
              "disclosure, so this is the dial\n           `[emission] scent` exists for.")
    else:
        print(f"    cells: both {ours['cells_median']} (median) — comparable disclosure")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default=DEFAULT_EVENTS)
    parser.add_argument("--since", default="", help="ISO timestamp prefix, inclusive")
    parser.add_argument("--until", default="9999", help="ISO timestamp prefix, inclusive")
    args = parser.parse_args()
    return report(ROOT / args.events, args.since, args.until)


if __name__ == "__main__":
    raise SystemExit(main())
