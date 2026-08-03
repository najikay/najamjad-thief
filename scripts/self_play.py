"""Measure whether our brains actually beat the obvious strategy.

    uv run python scripts/self_play.py --games 100 --seed 7

Runs seeded mini-games through the *real* match machinery — orchestrator, turn
loop, commit-reveal, audit — rather than a simplified loop. That distinction
matters: the contradictory-report defect that voided every capture only showed
up when two peers actually played each other, and a harness that shortcuts the
protocol would have missed it too.

Writes one JSON line per game plus a summary, so a regression shows up as a
changed win rate rather than a vague feeling.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from najamjad_agent.constants import EndReason, Role  # noqa: E402
from najamjad_agent.domain.match import MatchRunner  # noqa: E402
from najamjad_agent.domain.scoring import ScoreTable  # noqa: E402
from najamjad_agent.domain.series import SeriesTracker  # noqa: E402
from najamjad_agent.strategy.cop_brain import CopBrain  # noqa: E402
from najamjad_agent.strategy.thief_brain import ThiefBrain  # noqa: E402
from tests.fakes.baselines import GreedyCop, GreedyThief  # noqa: E402
from tests.fakes.network import linked_pair  # noqa: E402
from tests.fakes.orchestration import FakeClock, FixedSpeaker, build_state  # noqa: E402
from tests.integration.test_headless_game import SCORING  # noqa: E402

MATCHUPS = {
    "ours_cop_vs_greedy_thief": (CopBrain, GreedyThief, Role.COP),
    "ours_thief_vs_greedy_cop": (GreedyCop, ThiefBrain, Role.THIEF),
    "greedy_vs_greedy": (GreedyCop, GreedyThief, Role.COP),
}


def _runner(link, brain_class, role: Role, start) -> MatchRunner:
    """One peer, playing a single mini-game in a fixed role."""
    board = build_state(Role.COP).board

    def make_state(_params, for_role: Role, sub_game: int):
        state = build_state(for_role, position=start)
        state.sub_game = sub_game
        return state

    def make_brain(_role: Role, state):
        # The board is read live so a barrier placed this turn is visible next.
        return brain_class(board_supplier=lambda: state.board)

    return MatchRunner(
        params=board.params,
        tracker=SeriesTracker(
            our_group="us",
            their_group="them",
            table=ScoreTable.from_config(SCORING),
            first_role=role,
            total_games=1,
        ),
        transport=link,
        build_state=make_state,
        build_brain=make_brain,
        speaker=FixedSpeaker(),
        clock=FakeClock(),
        first_role=role,
        # Two real threads exchanging real messages, so this is a budget for the
        # *machine*, not for the agent. At 0.2 s it was measuring load: under a
        # full test suite a peer misses the window, the mini-game records a
        # timeout, its audit is skipped, and `audit_failures` goes non-zero — a
        # self-play harness reporting voided games because the laptop was busy.
        # It cost two red CI runs that looked like a correctness regression and
        # passed 4/4 in isolation. Generous here is free; the real deadline is
        # the negotiated 30 s and lives in `config/`, not in a test harness.
        response_timeout=5.0,
        max_retries=2,
        audit_timeout=10.0,
    )


def play_one(cop_brain, thief_brain, cop_start, thief_start) -> dict:
    """Play one full mini-game between two peers; report what happened."""
    left, right = linked_pair()
    cop = _runner(left, cop_brain, Role.COP, cop_start)
    thief = _runner(right, thief_brain, Role.THIEF, thief_start)
    threads = [threading.Thread(target=r.play_series, daemon=True) for r in (cop, thief)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    if not cop.games or not thief.games:
        return {"outcome": "stalled", "cop_start": list(cop_start), "thief_start": list(thief_start)}
    return {
        "outcome": cop.games[0]["end_reason"],
        "steps": cop.games[0]["steps"],
        "audit": cop.games[0]["audit"],
        "agreed": cop.games[0]["end_reason"] == thief.games[0]["end_reason"],
        "cop_start": list(cop_start),
        "thief_start": list(thief_start),
    }


def run(games: int, seed: int, out: Path | None) -> dict:
    """Run every matchup `games` times from seeded starting positions."""
    rng = random.Random(seed)
    size = build_state(Role.COP).board.size
    starts = [
        ((rng.randrange(size), rng.randrange(size)), (rng.randrange(size), rng.randrange(size)))
        for _ in range(games)
    ]
    summary: dict[str, dict] = {}
    handle = out.open("w", encoding="utf-8") if out else None
    try:
        for name, (cop_cls, thief_cls, _first) in MATCHUPS.items():
            rows = []
            for index, (cop_start, thief_start) in enumerate(starts):
                if cop_start == thief_start:  # a game that starts captured proves nothing
                    continue
                row = play_one(cop_cls, thief_cls, cop_start, thief_start)
                row.update({"matchup": name, "game": index})
                rows.append(row)
                if handle:
                    handle.write(json.dumps(row) + "\n")
            summary[name] = _summarise(rows)
            print(f"{name:28} {summary[name]['captures']}/{summary[name]['played']} captures")
    finally:
        if handle:
            handle.close()
    return summary


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score interval for a proportion.

    Wilson rather than the normal approximation because our sample sizes are
    small and the rates land near 0 and 1, exactly where the normal interval
    runs past those bounds and reports a confidence range that cannot occur.
    """
    if trials == 0:
        return (0.0, 0.0)
    phat = successes / trials
    denominator = 1 + z**2 / trials
    centre = (phat + z**2 / (2 * trials)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / trials + z**2 / (4 * trials**2)) / denominator
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def _summarise(rows: list[dict]) -> dict:
    """Capture rate, its confidence interval, and health signals."""
    played = len(rows)
    captures = sum(1 for row in rows if row.get("outcome") == EndReason.CAPTURE.value)
    steps = [row["steps"] for row in rows if isinstance(row.get("steps"), int)]
    low, high = wilson_interval(captures, played)
    return {
        "played": played,
        "captures": captures,
        "capture_rate": round(captures / played, 4) if played else 0.0,
        # Reported alongside the rate so a difference between two runs can be
        # read as signal or noise instead of guessed at.
        "capture_rate_ci95": [low, high],
        "mean_steps": round(sum(steps) / len(steps), 2) if steps else 0.0,
        "by_end_reason": dict(Counter(row.get("outcome", "?") for row in rows)),
        "disagreements": sum(1 for row in rows if row.get("agreed") is False),
        "stalled": sum(1 for row in rows if row.get("outcome") == "stalled"),
        "audit_failures": sum(1 for row in rows if row.get("audit") not in (None, "Verified OK")),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the harness and print the summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None, help="JSONL results file")
    args = parser.parse_args(argv)

    summary = run(args.games, args.seed, args.out)
    print(json.dumps(summary, indent=1))
    unhealthy = [
        name
        for name, stats in summary.items()
        if stats["disagreements"] or stats["stalled"] or stats["audit_failures"]
    ]
    if unhealthy:
        print(f"UNHEALTHY: {', '.join(unhealthy)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
