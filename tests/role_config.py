"""Load whichever role config this repo actually ships.

The two repos share a byte-identical test suite but not their configs: the cop
repo has `config/police/`, the thief repo has `config/thief/`. A test that names
one of them passes at home and fails in the twin — which is exactly what two
tests written today did, and the cross-repo gate is the only thing that noticed.
"""

from __future__ import annotations

import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def role_config_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """The private config directory for whichever role this repo plays."""
    base = (root or REPO_ROOT) / "config"
    for name in ("police", "thief"):
        candidate = base / name
        if candidate.is_dir():
            return candidate
    raise AssertionError(f"no role config directory under {base}")


def load_role_config(root: pathlib.Path | None = None) -> Any:
    """A `ConfigManager` over this repo's own role plus the shared terms."""
    from najamjad_agent.shared.config import ConfigManager

    base = root or REPO_ROOT
    return ConfigManager.load(role_config_dir(base), shared_config=base / "config/game.json")
