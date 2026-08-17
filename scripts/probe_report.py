"""Score a finished warm-up and record which candidate to play for keeps.

Run this after a probe series:

    uv run python scripts/probe_report.py                 # print the ranking
    uv run python scripts/probe_report.py --apply         # and save the winners

Attribution needs no new field in the report, and deliberately so: the window to
candidate mapping in `strategy/variants.for_window` is a pure function, so which
candidate played sub-game 4 is recomputed here rather than trusted from a log.
There is nothing to disagree with.

Steps come from the per-game log artifact when it is present. In a split series
each process holds only its own three, and the sibling's are absent — so a missing
count falls back to the full 35, which is neutral: it is the worst tie-break for a
cop and the best for a thief, and the primary key is always capture versus
survival, which the merged report carries for all six.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from najamjad_agent.sdk.probe import rank, save_choice, winners  # noqa: E402
from najamjad_agent.strategy.variants import for_window  # noqa: E402

ARTIFACTS = "workspace/artifacts"
MAX_STEPS = 35


def latest_result(root: Path) -> Path | None:
    """The most recently written result artifact, or nothing to score."""
    found = sorted(glob.glob(str(root / ARTIFACTS / "result_*.json")), key=lambda p: Path(p).stat().st_mtime)
    return Path(found[-1]) if found else None


def steps_for(root: Path, game_id: str, number: int) -> int:
    """How long that mini-game ran, from its own log when we hold it."""
    path = root / ARTIFACTS / f"log_{game_id}_g{number:02d}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        ours = [r for r in body.get("records", []) if isinstance(r.get("payload", {}).get("step"), int)]
        return max((r["payload"]["step"] for r in ours), default=MAX_STEPS)
    except Exception:  # noqa: BLE001 - an absent sibling half is normal, not a fault
        return MAX_STEPS


def rows_from(root: Path, report: dict) -> tuple[str, list[dict]]:
    """One row per window: the candidate that played it and how it ended."""
    game_id = str(report.get("game_id", ""))
    us = "najamjad"
    them = next((g for g in report.get("groups", []) if g != us), "unknown")
    rows = []
    for game in report.get("sub_games", []):
        number = int(game.get("sub_game_number", 0))
        role = str((game.get("roles") or {}).get(us, ""))
        side = "cop" if role == "police" else "thief"
        rows.append({
            "sub_game": number,
            "side": side,
            "variant": for_window(side, number).name,
            "end_reason": str(game.get("result", "")),
            "steps": steps_for(root, game_id, number),
            "score": (game.get("score") or {}).get(us, 0),
        })
    return them, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="save the winners for the counted run")
    parser.add_argument("--root", default=".", help="repository to read artifacts from")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    path = latest_result(root)
    if path is None:
        print(f"no result artifact under {root / ARTIFACTS} — nothing to score")
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    them, rows = rows_from(root, report)
    if not rows:
        print(f"{path.name} carries no sub-games")
        return 1

    print(f"\nprobe against {them}   ({path.name}, {len(rows)} windows)\n")
    for side in ("thief", "cop"):
        ours = [row for row in rows if row["side"] == side]
        if not ours:
            continue
        print(f"  as {side}")
        for place, row in enumerate(rank(ours), 1):
            mark = "  <== best" if place == 1 else ""
            print(f"    {place}. {row['variant']:<9} g{row['sub_game']:02d} "
                  f"{row['end_reason']:<9} {row['steps']:>2} steps  "
                  f"{row['score']:>2} pts{mark}")
        print()

    picks = winners(rows)
    print(f"  would play for keeps: {picks or '(nothing to choose from)'}")
    if args.apply and picks:
        written = save_choice(root, them, picks, rows)
        print(f"  saved to {written.relative_to(root)} — the counted run loads it with no flag")
    elif picks:
        print("  re-run with --apply to save it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
