"""Rebuilding the board at each step from the revealed records.

The state string sealed into every commit (`grid=7x7;self=[4, 3];barriers=[]`)
is the authoritative source: it is inside the hash, so a step that verifies has
a board nobody could have edited afterwards. Where a log carries a friendlier
`position` field too, the state string still wins — a mismatch between them is
itself worth showing rather than smoothing over.

Step 0 is the signed step-zero record (system spec, code version, github_commit)
and has no board at all, so every accessor here tolerates its absence.
"""

import re
from typing import Any

GRID = re.compile(r"grid=(\d+)x(\d+)")
SELF = re.compile(r"self=\[\s*(\d+)\s*,\s*(\d+)\s*\]")
BARRIERS = re.compile(r"barriers=(\[.*?\])\s*$")
CELL = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]")


def parse_state(state: Any) -> dict[str, Any]:
    """Pull grid size, own cell and barriers out of a sealed state string."""
    if not isinstance(state, str):
        return {}
    parsed: dict[str, Any] = {}
    grid = GRID.search(state)
    if grid:
        parsed["size"] = int(grid.group(1))
    own = SELF.search(state)
    if own:
        parsed["position"] = [int(own.group(1)), int(own.group(2))]
    barriers = BARRIERS.search(state)
    if barriers:
        parsed["barriers"] = [
            [int(row), int(col)] for row, col in CELL.findall(barriers.group(1))
        ]
    return parsed


def _disagreement(parsed: dict[str, Any], payload: dict[str, Any]) -> str:
    """Report a `position` field that contradicts the sealed state string."""
    stated, listed = parsed.get("position"), payload.get("position")
    if stated is None or listed is None or list(listed) == stated:
        return ""
    return f"position {list(listed)} contradicts the sealed state {stated}"


def step_view(record: dict[str, Any], verdict: Any, index: int) -> dict[str, Any]:
    """Everything the viewer draws for one step."""
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    parsed = parse_state(payload.get("state"))
    return {
        "index": index,
        "step": verdict.step,
        "verified": verdict.verified,
        "reason": verdict.reason,
        "commit": verdict.commit,
        "recomputed": verdict.recomputed,
        "kind": payload.get("type", "turn"),
        "size": parsed.get("size", 0),
        "position": parsed.get("position"),
        "barriers": parsed.get("barriers", []),
        "move": payload.get("move", ""),
        "intent": payload.get("intent") or payload.get("verdict", ""),
        "hint": payload.get("hint", ""),
        "model": payload.get("model", ""),
        "tokens": payload.get("tokens_step", 0),
        "warning": _disagreement(parsed, payload),
    }


def timeline(result: Any) -> list[dict[str, Any]]:
    """Per-step views for the whole log, in record order."""
    return [
        step_view(record, verdict, index)
        for index, (record, verdict) in enumerate(zip(result.records, result.steps, strict=True))
    ]


def summary_view(result: Any) -> dict[str, Any]:
    """The header: banner, counts, and whatever metadata the log carried."""
    document = result.document
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    return {
        "banner": result.banner,
        "passed": result.passed,
        "void": result.void,
        "steps": len(result.steps),
        "verified": sum(1 for step in result.steps if step.verified),
        "failed": result.failed_indices,
        "errors": list(result.report.errors),
        "game_id": document.get("game_id", ""),
        "game_uid": document.get("game_uid", ""),
        "role": summary.get("role", ""),
        "result": summary.get("result", ""),
        "winner_role": summary.get("winner_role", ""),
    }
