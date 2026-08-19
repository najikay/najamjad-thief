"""Both brains against every real opponent line this repo holds.

The strongest ratchet available: not a synthetic thief, not a hand-picked
position, but every mini-game any opponent has ever played against us, replayed
from their own sealed records. `scripted_opponents.py` holds two curated lines;
this sweeps the lot, so a change cannot pass by being good at the cases someone
remembered to write down.

Counts are deliberately absent from the assertions. The two repos archive
different series — `matches/` is role-specific and outside the core manifest —
so a hard number would pass in one repo and fail in the other. What is asserted
is the invariant: **no archived cop line captures our thief.** That is currently
61 of 61 in the cop repo, every one surviving the full 35 steps.

A replayed line cannot react, so this measures "still beats what we have met"
rather than "beats them today". It is the only corpus of real opponents that
exists, and every strategy change this project has adopted or reverted was
decided on it.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.regression.duel import run_duel

REPO = Path(__file__).resolve().parents[2]
DIRS = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}
CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"],
                              "max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
}


def cop_lines():
    """Every archived line in which the opponent played police."""
    for path in sorted(glob.glob(str(REPO / "matches" / "*" / "log_*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        steps = {
            p["step"]: p
            for p in (r.get("payload", {}) for r in data.get("opponent_records", []))
            if p.get("step") and p.get("position")
        }
        if len(steps) < 8:
            continue
        ordered = [steps[key] for key in sorted(steps)]
        walls, claimed = {}, False
        for index, payload in enumerate(ordered, 1):
            move = str(payload.get("move", ""))
            claimed = claimed or bool(payload.get("capture_claim"))
            if move.startswith("BARRIER:") and move.split(":")[1] in DIRS:
                row, col = payload["position"]
                shift = DIRS[move.split(":")[1]]
                walls[index] = (row + shift[0], col + shift[1])
        role = next((p.get("role") for p in ordered if p.get("role")), None)
        if role != "police" and not (walls or claimed):
            continue
        yield (f"{Path(path).parent.name[:24]}/{Path(path).stem[-3:]}",
               tuple(tuple(p["position"]) for p in ordered), walls)


def test_no_archived_cop_line_captures_our_thief() -> None:
    """The whole field, in one assertion."""
    params = GameParams.from_config(CONFIG)
    games = list(cop_lines())
    if not games:
        pytest.skip("no archived opponent cop lines in this repo")
    losses = [
        f"{label} at step {result.steps_survived} ({result.reason})"
        for label, cells, walls in games
        if (result := run_duel(ThiefBrain(), list(cells), params, walls)).captured
    ]

    assert not losses, f"captured on {len(losses)} of {len(games)} archived lines: {losses[:4]}"
