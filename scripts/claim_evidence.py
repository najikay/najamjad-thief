"""What a capture claim is worth, measured rather than argued (T-2610).

    uv run python scripts/claim_evidence.py

Three sessions disagreed about whether a capture claim should feed the belief as
a fix on the cop's own cell, and two of them removed the wiring. The argument
each time was semantic — does the claimed cell name the cop or the thief? — and
it could not be settled by reading our own receiving code, because
`answer_capture_claim(true_thief_cell, claimed_cell)` is the same line under
either reading. This settles it from the senders, and then from outcomes.

**Part 1 — semantics.** Every sealed record in `matches/` that carries both a
`capture_claim` and the claimer's revealed `position`, compared. 323 of 323
agree. Both reference implementations send `list(rt.state.position)` when POLICE
moves, and our own cop is locked to its own true cell by T-0535.

**Part 2 — outcomes.** Every archived mini-game in which the opponent played cop
and claimed, replayed through the real `absorb_turn` and `decay_after_full_turn`
with their declarations on the steps they were really declared on, once reading
claims and once ignoring them. Also replayed with their claims replaced by two
hostile policies, because the case for ignoring rested entirely on those.

Re-run it after touching `cop_sighting`, `turn_ingress` or `belief`.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from najamjad_agent.domain.board import Board  # noqa: E402
from najamjad_agent.domain.params import GameParams  # noqa: E402
from najamjad_agent.strategy.thief_brain import ThiefBrain  # noqa: E402
from tests.regression.duel import run_duel  # noqa: E402
from tests.regression.silent_peer import SilentPeerBelief  # noqa: E402

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14, "max_moves": 35, "survival_threshold": 35,
    },
}
PARAMS = GameParams.from_config(CONFIG)


def archived_games():
    """Opponent cop lines, with barriers and claims keyed by their real steps."""
    for path in sorted(glob.glob(str(ROOT.parent / "najamjad-*/matches/*/log_*.json"))):
        data = json.loads(Path(path).read_text())
        steps = {}
        for record in data.get("opponent_records", []):
            payload = record.get("payload", {})
            if payload.get("step") and payload.get("position"):
                steps[payload["step"]] = payload
        ordered = [steps[key] for key in sorted(steps)]
        if len(ordered) < 8:
            continue
        yield {
            "label": f"{Path(path).parent.name[:20]}/{Path(path).stem[-3:]}",
            "cells": tuple(tuple(p["position"]) for p in ordered),
            "walls": {i: tuple(p["barrier_placed"]) for i, p in enumerate(ordered, 1)
                      if isinstance(p.get("barrier_placed"), list)},
            "claims": {i: tuple(p["capture_claim"]) for i, p in enumerate(ordered, 1)
                       if isinstance(p.get("capture_claim"), list)},
        }


def semantics() -> None:
    """Does a claim name the cell the claimer reveals standing on?"""
    same = differ = 0
    for game in archived_games():
        for step, claimed in game["claims"].items():
            if claimed == game["cells"][step - 1]:
                same += 1
            else:
                differ += 1
                print(f"  MISMATCH {game['label']} step {step}: "
                      f"claimed {claimed}, revealed {game['cells'][step - 1]}")
    print(f"claims naming the claimer's own revealed cell: {same} of {same + differ}")
    if differ:
        print("  ** a peer has claimed a cell it was not standing on. `from_claim`"
              " rests on this never happening — re-read it before the next match. **")


def _replay(game, claims):
    """Their line and walls, with `claims` as the claim policy. Returns (result, err)."""
    belief = SilentPeerBelief(PARAMS, game["cells"], game["walls"])
    belief._message = lambda cop, step: {  # noqa: SLF001
        "step": step, "commit": f"{step:064x}",
        **({"capture_claim": list(claims(cop, step))} if claims(cop, step) else {}),
        **({"barrier_placed": list(game["walls"][step])} if step in game["walls"] else {}),
    }
    errors: list[int] = []
    exact = 0

    def watched(cop, step, thief):
        distribution = belief(cop, step, thief)
        peak = belief.peak
        if peak is not None:
            errors.append(Board.manhattan(peak, cop))
        return distribution

    result = run_duel(ThiefBrain(), game["cells"], PARAMS, game["walls"], belief_for=watched)
    exact = sum(1 for value in errors if value == 0)
    turns = len(errors) or 1
    return result, sum(errors) / turns, exact / turns


def outcomes() -> None:
    """What reading them, and refusing to, actually does to the games we have."""
    games = [g for g in archived_games() if len(g["claims"]) >= 5]
    seen, unique = set(), []
    for game in games:
        key = (game["cells"], tuple(sorted(game["walls"].items())))
        if key not in seen:
            seen.add(key)
            unique.append(game)
    policies = {
        "their real claims": lambda game: (lambda cop, step: game["claims"].get(step)),
        "ignored (the old behaviour)": lambda game: (lambda cop, step: None),
        "hostile: one row off": lambda game: (lambda cop, step: ((cop[0] + 1) % 7, cop[1])),
        "hostile: always our cell": lambda game: (lambda cop, step: PARAMS.thief_start),
    }
    print(f"\n{len(unique)} distinct archived lines on which the opponent claimed")
    for name, build in policies.items():
        print(f"\n  {name}")
        for game in unique:
            result, error, exact = _replay(game, build(game))
            verdict = "survived 35" if result.survived else f"CAPTURED at {result.steps_survived}"
            print(f"    {game['label']:<26} {verdict:<20} "
                  f"mean belief error {error:.2f}, exact on {exact:.0%} of turns")


if __name__ == "__main__":
    semantics()
    outcomes()
