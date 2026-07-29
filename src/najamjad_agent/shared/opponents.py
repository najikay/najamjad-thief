"""One file per opponent — the details you must agree before a match.

Two settings decide who we play: their MCP endpoint and their `group_id`.
Both were edited by hand into `config/<role>/game.toml` before every match,
which is a tracked file, so preparing for a match dirtied the repository and
the settings for the *last* opponent were overwritten by the next.

That is worse than untidy. `opponent_group_id` must equal what their handshake
declares or the filer's rename never fires and the emitted result is keyed by a
placeholder; and a mistyped URL is discovered at the handshake, not before. A
per-opponent file makes both reviewable in advance, keeps the shipped config
clean, and leaves a record of who we played on what address — which the runbook
wants anyway for the per-match archive.

The card carries only the two negotiable-with-a-human facts plus notes. It is
deliberately *not* a second place to set game terms: those are agreed in
`config/game.json` and signed, and a per-opponent override of a signed term is
the one thing that must never be easy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib

DEFAULT_ROOT = Path("opponents")


class OpponentError(RuntimeError):
    """The named opponent card is missing or unusable."""


def available(root: Path | str = DEFAULT_ROOT) -> list[str]:
    """Every opponent we have a card for, without the extension."""
    base = Path(root)
    if not base.is_dir():
        return []
    return sorted(p.stem for p in base.glob("*.toml") if not p.name.startswith(("_", ".")))


def load_opponent(name: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """Read one opponent card, or fail naming the cards that do exist.

    Input: the card's filename without `.toml`.
    Output: `{"url": ..., "group_id": ..., "name": ..., "notes": ...}`.
    Setup: a `opponents/<name>.toml` file; see `opponents/_template.toml`.

    The error lists what is available because the person reading it is usually
    minutes from a match and has mistyped a name.
    """
    path = Path(root) / f"{name}.toml"
    if not path.exists():
        known = ", ".join(available(root)) or "none yet"
        raise OpponentError(f"no opponent card at {path} — available: {known}")
    try:
        card = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise OpponentError(f"{path} could not be read: {error}") from error

    missing = [key for key in ("url", "group_id") if not str(card.get(key, "")).strip()]
    if missing:
        raise OpponentError(f"{path} is missing {', '.join(missing)}")
    return card


def as_overlay(card: dict[str, Any]) -> dict[str, Any]:
    """The card in the shape `ConfigManager.overlay` merges.

    Only `network.*` is touched. An opponent card cannot reach a signed game
    term, and keeping the mapping this narrow is what guarantees it.
    """
    return {
        "network": {
            "opponent_url": str(card["url"]).strip(),
            "opponent_group_id": str(card["group_id"]).strip(),
        }
    }
