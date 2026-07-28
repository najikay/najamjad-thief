"""Seeded strategy smoke and the cross-play matrix (T-1421, T-1520, T-1523).

    uv run python scripts/strategy_smoke.py --games 50

Three questions, each answered over seeded games through the real match
machinery:

* does the cop capture the baseline thief at least 70 % of the time;
* does the thief survive the baseline cop at least 70 % of the time;
* what happens when our two brains play **each other** — the cross-play matrix
  the notebook reports, and the number that tells us whether our thief is weak
  or our cop is strong.

Deliberately *not* a CI gate. A win rate is a sample, and a flaky gate teaches
people to ignore red builds; `docs/CI.md` says so and the nightly workflow is
where this belongs. The floors here are alarms set well below measured
performance, not targets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from najamjad_agent.constants import Role  # noqa: E402
from najamjad_agent.strategy.cop_brain import CopBrain  # noqa: E402
from najamjad_agent.strategy.thief_brain import ThiefBrain  # noqa: E402
from scripts.self_play import play_one, wilson_interval  # noqa: E402
from tests.fakes.baselines import GreedyCop, GreedyThief  # noqa: E402
from tests.fakes.orchestration import build_state  # noqa: E402

COP_FLOOR = 0.70
THIEF_FLOOR = 0.70
MATCHUPS = {
    "cop_vs_baseline": (CopBrain, GreedyThief),
    "thief_vs_baseline": (GreedyCop, ThiefBrain),
    "cross_play": (CopBrain, ThiefBrain),
}


def seeded_starts(games: int, seed: int) -> list[tuple]:
    """Start pairs that never begin already captured."""
    import random

    rng = random.Random(seed)
    size = build_state(Role.COP).board.size
    pairs = []
    while len(pairs) < games:
        cop = (rng.randrange(size), rng.randrange(size))
        thief = (rng.randrange(size), rng.randrange(size))
        if cop != thief:
            pairs.append((cop, thief))
    return pairs


def run_matchup(name: str, games: int, seed: int) -> dict:
    """Play one matchup over every seeded start."""
    cop_cls, thief_cls = MATCHUPS[name]
    rows = [play_one(cop_cls, thief_cls, cop, thief) for cop, thief in seeded_starts(games, seed)]
    played = len(rows)
    captures = sum(1 for row in rows if row.get("outcome") == "capture")
    low, high = wilson_interval(captures, played)
    return {
        "matchup": name,
        "played": played,
        "captures": captures,
        "capture_rate": round(captures / played, 4) if played else 0.0,
        "capture_rate_ci95": [low, high],
        "survival_rate": round(1 - captures / played, 4) if played else 0.0,
        "disagreements": sum(1 for row in rows if row.get("agreed") is False),
        "audit_failures": sum(1 for row in rows if row.get("audit") not in (None, "Verified OK")),
        "stalled": sum(1 for row in rows if row.get("outcome") == "stalled"),
    }


def verdict(results: dict[str, dict]) -> list[str]:
    """Which floors were missed, if any."""
    problems = []
    cop = results["cop_vs_baseline"]
    thief = results["thief_vs_baseline"]
    if cop["capture_rate"] < COP_FLOOR:
        problems.append(f"cop captured {cop['capture_rate']:.0%} < {COP_FLOOR:.0%}")
    if thief["survival_rate"] < THIEF_FLOOR:
        problems.append(f"thief survived {thief['survival_rate']:.0%} < {THIEF_FLOOR:.0%}")
    for name, row in results.items():
        if row["disagreements"] or row["audit_failures"] or row["stalled"]:
            problems.append(
                f"{name}: {row['disagreements']} disagreements, "
                f"{row['audit_failures']} audit failures, {row['stalled']} stalled"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run every matchup and report one verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out", type=Path, default=ROOT / "results/strategy_smoke.json")
    args = parser.parse_args(argv)

    results = {name: run_matchup(name, args.games, args.seed) for name in MATCHUPS}
    for name, row in results.items():
        print(f"  {name:20} captures {row['captures']:3}/{row['played']:<3} "
              f"({row['capture_rate']:.0%})  survival {row['survival_rate']:.0%}  "
              f"CI{row['capture_rate_ci95']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"seed": args.seed, "games": args.games, "matchups": results}, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {args.out}")

    problems = verdict(results)
    print("-" * 68)
    if problems:
        print("STRATEGY SMOKE FAILED:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("STRATEGY SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
