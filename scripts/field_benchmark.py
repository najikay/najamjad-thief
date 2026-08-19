"""Both brains against the whole league, from real sealed logs.

Every mini-game either side has ever played against us is in `matches/`, with
the opponent's revealed positions, barriers and claims. This replays all of it:
our thief against every real cop line we hold, our cop against every real thief
line. A replayed line does not react, so this measures "do we still beat what
we have already met" — not "would we beat them today". It is the only corpus of
*real* opponents in existence, and no synthetic thief substitutes for it.
"""

from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.cop_duel import run_cop_duel
from tests.regression.duel import run_duel

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DIRS = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}
CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"],
                              "max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
}


def team_of(path: str) -> str:
    name = Path(path).parent.name
    for known in ("uoh-sqak", "uoh-ay26", "imreeyal", "vibecode", "moaamoha", "yanell11",
                  "ahk-yosi", "amjad", "sparring", "MOAAMOHA"):
        if name.lower().startswith(known.lower()):
            return known
    return name.split("-")[0]


def lines():
    """Every archived opponent line, keyed by the role they played."""
    for path in sorted(set(glob.glob(f"{ROOT}/najamjad-*/matches/*/log_*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as unreadable:
            print(f"  skipping {Path(path).name}: {unreadable}")
            continue
        steps = {}
        for record in data.get("opponent_records", []):
            payload = record.get("payload", {})
            if payload.get("step") and payload.get("position"):
                steps[payload["step"]] = payload
        if len(steps) < 8:
            continue
        ordered = [steps[k] for k in sorted(steps)]
        walls, claimed = {}, False
        for index, payload in enumerate(ordered, 1):
            move = str(payload.get("move", ""))
            if payload.get("capture_claim"):
                claimed = True
            if move.startswith("BARRIER:"):
                row, col = payload["position"]
                delta = DIRS.get(move.split(":")[1])
                if delta:
                    walls[index] = (row + delta[0], col + delta[1])
            elif isinstance(payload.get("barrier_placed"), list):
                walls[index] = tuple(payload["barrier_placed"])
        role = next((p.get("role") for p in ordered if p.get("role")), None)
        if role not in ("police", "thief"):
            role = "police" if (walls or claimed) else "thief"
        yield {"team": team_of(path), "label": f"{Path(path).parent.name[:22]}/{Path(path).stem[-3:]}",
               "role": role, "cells": tuple(tuple(p["position"]) for p in ordered), "walls": walls}


def main() -> None:
    params = GameParams.from_config(CONFIG)
    thief_rows, cop_rows = defaultdict(list), defaultdict(list)
    for game in lines():
        if game["role"] == "police":
            result = run_duel(ThiefBrain(), list(game["cells"]), params, game["walls"])
            thief_rows[game["team"]].append((not result.captured, result.steps_survived, len(game["walls"])))
        else:
            result = run_cop_duel(CopBrain(), list(game["cells"]), params)
            cop_rows[game["team"]].append((result.captured, result.step))

    print("OUR THIEF against every real cop line we hold\n")
    print(f"  {'opponent':<12}{'games':>6}{'survived':>10}{'mean steps':>12}{'their walls':>13}")
    total = survived = 0
    for team, rows in sorted(thief_rows.items()):
        lived = sum(1 for ok, _s, _w in rows if ok)
        total += len(rows)
        survived += lived
        print(f"  {team:<12}{len(rows):>6}{f'{lived}/{len(rows)}':>10}"
              f"{sum(s for _o, s, _w in rows)/len(rows):>12.1f}{sum(w for *_x, w in rows):>13}")
    print(f"  {'TOTAL':<12}{total:>6}{f'{survived}/{total}':>10}   ({survived/max(total,1):.0%})")

    print("\nOUR COP against every real thief line we hold\n")
    print(f"  {'opponent':<12}{'games':>6}{'captured':>10}{'mean step':>11}")
    total = caught = 0
    for team, rows in sorted(cop_rows.items()):
        got = sum(1 for hit, _s in rows if hit)
        steps = [s for hit, s in rows if hit]
        total += len(rows)
        caught += got
        print(f"  {team:<12}{len(rows):>6}{f'{got}/{len(rows)}':>10}"
              f"{(sum(steps)/len(steps) if steps else 0):>11.1f}")
    print(f"  {'TOTAL':<12}{total:>6}{f'{caught}/{total}':>10}   ({caught/max(total,1):.0%})")


if __name__ == "__main__":
    main()
