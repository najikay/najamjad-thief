"""Per-opponent match folders — one place per match, nothing shared.

A league evening produces four artifacts, an incident log and a profile per
opponent, several times over. Writing them all into one directory makes the
first question after a match — *which files belong to which game* — a matter of
reading timestamps, and Appendix F names files by `game_id` precisely so that
never happens.

So each match gets `matches/<opponent>/`, and the opponent's name is sanitised
on the way in: it arrives from the wire, in a field they control, and it is
about to become a path.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Anything outside this becomes a dash. Deliberately strict — a group id is
#: an identifier, not free text, and this one is used to build a filesystem path.
SAFE = re.compile(r"[^A-Za-z0-9._-]+")
FALLBACK = "unknown-opponent"
MAX_NAME = 64


def safe_name(opponent: str) -> str:
    """A group id reduced to something safe to use as a directory name.

    The opponent chooses this string and sends it to us. `../../etc` and an
    empty name are both things a peer can say, and neither may become a path we
    write to.
    """
    cleaned = SAFE.sub("-", (opponent or "").strip()).strip("-.")
    return (cleaned[:MAX_NAME] or FALLBACK).lower()


def match_dir(opponent: str, root: Path | str = "matches") -> Path:
    """The folder for one opponent's match, created if absent."""
    target = Path(root) / safe_name(opponent)
    target.mkdir(parents=True, exist_ok=True)
    return target


def artifact_dir(opponent: str, root: Path | str = "matches") -> Path:
    """Where this match's four artifacts live."""
    target = match_dir(opponent, root) / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    return target


def known_opponents(root: Path | str = "matches") -> list[str]:
    """Every opponent we have a folder for, in a stable order.

    Skips the template and anything hidden, so the list is what a human would
    call "matches we have played".
    """
    base = Path(root)
    if not base.is_dir():
        return []
    return sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and not entry.name.startswith((".", "_"))
    )
