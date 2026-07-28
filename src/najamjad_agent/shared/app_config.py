"""App-level settings — where files go and which subsystems run.

Separate from both other config files on purpose, and the distinction is the
point of the module:

* `game.json` is **agreed** with the opponent and signed;
* `<role>/game.toml` is **private** to this peer but still about the match;
* `setup.json` is about the **application** — paths, the local UI port, feature
  toggles — and would be the same whoever we played.

These were previously literals in `bootstrap` reached through `manager.get(...)`
with a default that nothing ever overrode, which is a hardcoded tunable wearing
a config lookup's clothes (guidelines §7.2, threshold zero).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("config/setup.json")


def load_setup(path: Path | str = DEFAULT_PATH) -> dict[str, Any]:
    """Read the app settings; an absent file is not fatal.

    A missing `setup.json` must not stop a match — the callers all pass a
    sensible default alongside the key, so the agent degrades to the behaviour
    it had before the file existed rather than refusing to start.
    """
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def setting(setup: dict[str, Any], dotted: str, default: Any) -> Any:
    """Read `"ui.port"` out of the loaded settings, or fall back.

    Underscore-prefixed keys are documentation for whoever opens the file and
    are never addressable, so a note can never shadow a setting.
    """
    node: Any = setup
    for part in dotted.split("."):
        if part.startswith("_") or not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def save_setup(setup: dict[str, Any], path: Path | str = DEFAULT_PATH) -> None:
    """Write the app settings back, preserving everything not being changed.

    Writing lives here rather than in the modules that toggle a flag, so
    `setup.json` has exactly one reader and one writer. Indented and
    `ensure_ascii=False` because a person edits this file by hand — deliberately
    *not* the canonical wire encoding, which is compact and sorted for audit
    stability and would make the config unreadable.
    """
    Path(path).write_text(
        json.dumps(setup, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
