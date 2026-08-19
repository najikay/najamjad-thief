"""Scoring a probe, and remembering what it decided.

The warm-up plays one candidate per window (`strategy/variants.py`); this reads
the outcomes back, ranks each role's three, and writes the winners where the next
build will find them. A counted run then loads the winner for this opponent and
plays it at full strength — no extra flag to remember at 20:00, which is exactly
when a flag gets forgotten.

Keyed by opponent, because the whole premise is that the right strategy is a
property of who we are playing. What beat MOAAMOHA's cornering thief is not what
beats a team that hides in open space.

**Nothing here may ever stop a match.** A missing file, a corrupt file, a name
that no longer exists in the roster — each resolves to "no opinion", and the
caller falls back to the shipped brain. Rule 35 scores a failure to play as a
loss, so a preference file is not permitted to cost a series.
"""

import json
from pathlib import Path
from typing import Any

#: Where the choice lives. Inside `workspace/`, which is untracked, because it is
#: a measurement about one opponent rather than a decision about our code.
CHOICE_FILE = "workspace/probe_choice.json"


def _key(opponent: str) -> str:
    """One opponent's slot, case-folded so a card's casing cannot split it."""
    return str(opponent or "unknown").strip().lower()


def score_key(side: str, end_reason: str, steps: int) -> tuple[int, int]:
    """Sortable rank for one window; lower is better.

    A cop wants a capture and wants it early. A thief wants to survive and, when
    it does not, wants to have lasted — so its step count sorts descending. Both
    read the same `end_reason` the report files, so a rank can always be
    recomputed from an artifact rather than trusted from this file.
    """
    reason = str(end_reason).strip().lower()
    if side == "cop":
        return (0 if reason == "capture" else 1, int(steps))
    return (0 if reason == "survival" else 1, -int(steps))


def rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Windows of one role, best first."""
    return sorted(rows, key=lambda row: score_key(
        str(row.get("side", "")), str(row.get("end_reason", "")), int(row.get("steps", 0))))


def winners(rows: list[dict[str, Any]]) -> dict[str, str]:
    """The best-scoring candidate name per role, from a probe's windows."""
    picks: dict[str, str] = {}
    for side in ("cop", "thief"):
        ours = [row for row in rows if str(row.get("side")) == side and row.get("variant")]
        if ours:
            picks[side] = str(rank(ours)[0]["variant"])
    return picks


def save_choice(root: Path, opponent: str, picks: dict[str, str],
                evidence: list[dict[str, Any]] | None = None) -> Path:
    """Record the winners for this opponent, keeping any other opponent's."""
    path = Path(root) / CHOICE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    book = _read(path)
    book[_key(opponent)] = {"picks": picks, "evidence": evidence or []}
    path.write_text(json.dumps(book, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_choice(root: Path, opponent: str, side: str) -> str:
    """The remembered candidate for this opponent and role, or `""`.

    Deliberately total: every failure mode returns the empty string, so a caller
    can write `by_name(side, load_choice(...)) or shipped` and never branch on an
    exception path during a match.
    """
    try:
        entry = _read(Path(root) / CHOICE_FILE).get(_key(opponent), {})
        return str((entry.get("picks") or {}).get(side, "") or "")
    except Exception:  # noqa: BLE001 - a preference must never break a build
        return ""


def _read(path: Path) -> dict[str, Any]:
    """The choice book, or an empty one when it is absent or unreadable."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        return body if isinstance(body, dict) else {}
    except Exception:  # noqa: BLE001 - see `load_choice`
        return {}
