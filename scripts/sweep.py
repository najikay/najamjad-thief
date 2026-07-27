"""Parameter sweeps over the strategy tunables (T-2110).

    uv run python scripts/sweep.py --games 30 --seed 7

Varies one knob at a time (OAT) against a fixed baseline opponent and records
what it does to the outcome. One-at-a-time rather than a full grid because the
question is *sensitivity* — which dials matter — and a grid over four knobs
costs hundreds of games to answer the same thing less clearly.

Every game runs through the real match machinery, so a sweep also re-exercises
commit-reveal and the audit; a sweep that reported a tuning result while games
were silently voiding would be worse than no sweep.

Results land in `results/` as JSONL plus a summary, which is what the analysis
notebook reads.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from najamjad_agent.constants import EndReason, Role  # noqa: E402
from najamjad_agent.strategy.cop_brain import CopBrain  # noqa: E402
from najamjad_agent.strategy.thief_brain import ThiefBrain  # noqa: E402
from scripts.self_play import play_one, wilson_interval  # noqa: E402
from tests.fakes.baselines import GreedyCop, GreedyThief  # noqa: E402
from tests.fakes.orchestration import build_state  # noqa: E402

# The E14/E15 tunables, with the shipped value first in each list.
#
# `opponent` matters as much as the values. Swept against the greedy baseline,
# the cop captures 100 % and the thief survives 100 % at *every* setting of the
# two secondary knobs — a saturated result measures the opponent, not the knob.
# Those two are therefore swept against our own counterpart brain, which is the
# only opponent in reach that is strong enough to leave room to move.
SWEEPS = {
    "cop.barrier_threshold": {
        "values": [0.15, 0.05, 0.10, 0.25, 0.40, 0.60],
        "role": "cop",
        "opponent": "greedy",
        "why": "How confident the cop must be before spending one of 14 barriers.",
    },
    "cop.lookahead": {
        "values": [2, 1, 3, 4],
        "role": "cop",
        "opponent": "ours",
        "why": "How far belief is diffused forward before choosing a move.",
    },
    "thief.horizon": {
        "values": [3, 1, 2, 4, 5],
        "role": "thief",
        "opponent": "ours",
        "why": "How many steps ahead the thief protects its escape routes.",
    },
}


def brain_factory(role: str, knob: str, value: float):
    """A brain class bound to one tunable value, still taking `board_supplier`."""
    field = knob.split(".", 1)[1]

    def make(**kwargs):
        if role == "cop":
            typed = int(value) if field == "lookahead" else float(value)
            return CopBrain(**{**kwargs, field: typed})
        return ThiefBrain(**{**kwargs, field: int(value)})

    return make


def run_point(knob: str, value: float, role: str, starts: list, opponent: str = "greedy") -> dict:
    """Play every seeded start at one tunable value against one opponent."""
    rows = []
    rival_cop = GreedyCop if opponent == "greedy" else CopBrain
    rival_thief = GreedyThief if opponent == "greedy" else ThiefBrain
    for cop_start, thief_start in starts:
        if cop_start == thief_start:
            continue
        if role == "cop":
            cop, thief = brain_factory("cop", knob, value), rival_thief
        else:
            cop, thief = rival_cop, brain_factory("thief", knob, value)
        rows.append(play_one(cop, thief, cop_start, thief_start))

    played = len(rows)
    captures = sum(1 for row in rows if row.get("outcome") == EndReason.CAPTURE.value)
    low, high = wilson_interval(captures, played)
    # For the cop a capture is the win; for the thief it is the loss.
    win_rate = captures / played if role == "cop" else 1 - (captures / played)
    return {
        "knob": knob,
        "value": value,
        "role": role,
        "played": played,
        "captures": captures,
        "capture_rate": round(captures / played, 4) if played else 0.0,
        "capture_rate_ci95": [low, high],
        "win_rate": round(win_rate, 4) if played else 0.0,
        "disagreements": sum(1 for row in rows if row.get("agreed") is False),
        "audit_failures": sum(1 for r in rows if r.get("audit") not in (None, "Verified OK")),
        "rows": rows,
    }


def run(games: int, seed: int, out_dir: Path) -> dict:
    """Run every sweep and write the results."""
    rng = random.Random(seed)
    size = build_state(Role.COP).board.size
    starts = [
        ((rng.randrange(size), rng.randrange(size)), (rng.randrange(size), rng.randrange(size)))
        for _ in range(games)
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = (out_dir / f"sweep-{stamp}.jsonl").open("w", encoding="utf-8")
    summary: dict = {"seed": seed, "games_per_point": games, "generated": stamp, "sweeps": {}}
    try:
        for knob, spec in SWEEPS.items():
            points = []
            for value in spec["values"]:
                point = run_point(knob, value, spec["role"], starts, spec["opponent"])
                rows = point.pop("rows")
                lines.write(json.dumps({**point, "rows": rows}) + "\n")
                points.append(point)
                print(f"  {knob}={value!s:<6} win_rate={point['win_rate']:.2f} "
                      f"({point['captures']}/{point['played']} captures)")
            summary["sweeps"][knob] = {
                "why": spec["why"], "opponent": spec["opponent"], "points": points
            }
    finally:
        lines.close()
    (out_dir / f"summary-{stamp}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run the sweeps and report health."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=20, help="games per parameter value")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args(argv)

    summary = run(args.games, args.seed, args.out)
    bad = [
        f"{knob}={point['value']}"
        for knob, sweep in summary["sweeps"].items()
        for point in sweep["points"]
        if point["disagreements"] or point["audit_failures"]
    ]
    print(f"\nwrote {args.out}/latest.json")
    if bad:
        print(f"UNHEALTHY points: {', '.join(bad)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
