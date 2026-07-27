"""Head-to-head results against the reference baselines (T-2219).

    uv run python scripts/baselines.py --games 60 --seed 11

`self_play.py` is the harness; this is the *published run* of it whose numbers
the report quotes. It deliberately uses a different seed from the tuning sweeps
in `results/latest.json`: quoting the same games we tuned on would report how
well we fitted them, not how well we play.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.self_play import run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Run every matchup and write the summary the notebook plots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--seed", type=int, default=11, help="must differ from the tuning seed")
    parser.add_argument("--out", type=Path, default=ROOT / "results/baselines.json")
    args = parser.parse_args(argv)

    summary = run(args.games, args.seed, out=None)
    args.out.write_text(
        json.dumps(
            {"games": args.games, "seed": args.seed, "held_out_from_tuning": True,
             "matchups": summary},
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
