"""Breed thief strategies against the lines that actually beat us.

    uv run python scripts/evolve.py --rounds 12 --size 10 --seed 7

Everyone plays, the winner survives untouched, losers mutate, and a lineage that
keeps losing is redrawn rather than nudged again. The configuration we currently
ship is seeded into the population, so "we found something better" is a measured
claim and not a hope.

Deliberately in-process and deterministic rather than a swarm of LLM agents: a
duel is milliseconds, so this plays thousands of games in the time a handful of
agents would take to play a dozen, and every result replays exactly from its
seed. A tuning result nobody can reproduce is an opinion with a number on it.

Nothing here changes the shipped agent. It prints a genome and a comparison; the
adoption decision is a separate, deliberate edit, because the last time a
strategy was adopted on a weaker comparison it had to be reverted.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from najamjad_agent.domain.params import GameParams  # noqa: E402
from najamjad_agent.strategy import tournament  # noqa: E402
from najamjad_agent.strategy.thief_brain import ThiefBrain  # noqa: E402
from tests.regression.duel import run_duel  # noqa: E402
from tests.regression.scripted_opponents import (  # noqa: E402
    UOH_SQAK_BARRIERS,
    UOH_SQAK_SWEEP,
)
from tests.regression.silent_peer import SilentPeerBelief  # noqa: E402

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}


def _brain(genome) -> ThiefBrain:
    """A thief wired to one genome's dials."""
    return ThiefBrain(**genome.as_brain_kwargs())


def sweep_arena(params: GameParams):
    """uoh-sqak's recorded line, with the cop's cell known."""

    def play(genome) -> int:
        return run_duel(_brain(genome), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS).steps_survived

    return play


def silent_arena(params: GameParams):
    """The same line against a peer that transmits nothing.

    The arena that matters most: it is the one we were losing, and the one a
    perfect-information duel could not see at all.
    """

    def play(genome) -> int:
        belief = SilentPeerBelief(params, UOH_SQAK_SWEEP, UOH_SQAK_BARRIERS)
        return run_duel(
            _brain(genome), UOH_SQAK_SWEEP, params, UOH_SQAK_BARRIERS, belief_for=belief
        ).steps_survived

    return play


def corner_arena(params: GameParams):
    """A cop that walks straight at us from the far corner, no barriers.

    A second line so the search cannot overfit to one recorded opponent, which
    is the standard way a tuning run produces a strategy that beats exactly one
    team and nobody else.
    """
    chase = tuple((min(6, step), min(6, step)) for step in range(1, 36))

    def play(genome) -> int:
        return run_duel(_brain(genome), chase, params).steps_survived

    return play


def main() -> int:
    """Run the tournament and report whether it beat what we ship."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "evolve-latest.json")
    args = parser.parse_args()

    params = GameParams.from_config(CONFIG)
    arenas = [sweep_arena(params), silent_arena(params), corner_arena(params)]
    ceiling = len(arenas) * min(params.survival_threshold, params.max_moves)

    best, results = tournament.run(arenas, args.rounds, args.size, args.seed)
    incumbent = tournament.evaluate(tournament.Contender(tournament.genes.shipped()), arenas)
    champion = max(each.scores[each.champion] for each in results)

    print(f"arenas={len(arenas)} ceiling={ceiling} rounds={args.rounds} size={args.size}")
    print(f"shipped   : {incumbent}/{ceiling}")
    print(f"best found: {champion}/{ceiling}  ({best.name})")
    if champion > incumbent:
        print("\nA genome beat the shipped configuration:")
        print(json.dumps(dict(vars(best)), indent=2))
        print("\nNot adopted automatically. Re-run the regression gates against it first.")
    else:
        print("\nNothing beat the shipped configuration. Negative result, recorded.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "generated": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                "seed": args.seed,
                "ceiling": ceiling,
                "shipped_score": incumbent,
                "best_score": champion,
                "best_genome": dict(vars(best)),
                "rounds": [each.as_dict() for each in results],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
