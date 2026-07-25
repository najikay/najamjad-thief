"""Configuration: private TOML underneath, signed JSON on top.

The book's split (PAGE 127) is load-bearing, not cosmetic. `config/<role>/game.toml`
is ours alone — port, opponent URL, strategy choice, LLM settings — and never
crosses the network. `config/game.json` is the *signed contract*: byte-identical
on both peers, hashed, and refused on mismatch. So the JSON always overlays the
TOML: a private file must never be able to weaken an agreed term.

Everything is validated at load, not at use. Assignment 6 referenced a prompts
directory that did not exist and only found out mid-match; here a missing file
or an unsupported version stops the agent from booting at all.
"""

import copy
import json
from pathlib import Path
from typing import Any

import tomllib

from .version import SUPPORTED_CONFIG_VERSIONS


class ConfigError(Exception):
    """Raised when configuration is missing, stale, or internally inconsistent."""


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge `overlay` onto `base`, recursing into nested tables."""
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


class ConfigManager:
    """Loads, validates and exposes the merged configuration."""

    def __init__(self, values: dict[str, Any], sources: dict[str, Path] | None = None) -> None:
        """Wrap an already-merged mapping; prefer `load()` in production."""
        self._values = values
        self.sources = sources or {}

    @classmethod
    def load(
        cls,
        role_dir: Path,
        shared_config: Path | None = None,
        require_shared: bool = False,
    ) -> "ConfigManager":
        """Load `<role_dir>/game.toml` with an optional signed `game.json` overlay."""
        toml_path = role_dir / "game.toml"
        if not toml_path.exists():
            raise ConfigError(f"missing private config: {toml_path}")
        values = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        sources = {"toml": toml_path}
        if shared_config is not None and shared_config.exists():
            contract = json.loads(shared_config.read_text(encoding="utf-8"))
            values = _deep_merge(values, contract)
            sources["json"] = shared_config
        elif require_shared:
            raise ConfigError(f"signed contract not found: {shared_config}")
        manager = cls(values, sources)
        manager.validate()
        return manager

    def validate(self) -> None:
        """Check versions and referenced paths before anything runs."""
        version = str(self.get("version", ""))
        if version not in SUPPORTED_CONFIG_VERSIONS:
            raise ConfigError(
                f"config version {version!r} is not supported {SUPPORTED_CONFIG_VERSIONS}"
            )
        for key in ("strategy.prompt_file", "logging.config_file", "email.credentials_file"):
            referenced = self.get(key)
            if referenced and not Path(str(referenced)).expanduser().exists():
                raise ConfigError(f"{key} points at a missing file: {referenced}")

    def get(self, dotted: str, default: Any = None) -> Any:
        """Read a value by dotted path, e.g. `network.my_port`."""
        node: Any = self._values
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        """Read a value that must be present, raising a clear error if not."""
        value = self.get(dotted, None)
        if value is None:
            raise ConfigError(f"required configuration {dotted!r} is missing")
        return value

    def section(self, name: str) -> dict[str, Any]:
        """A whole table, or an empty mapping when absent."""
        value = self.get(name, {})
        return dict(value) if isinstance(value, dict) else {}

    def as_dict(self) -> dict[str, Any]:
        """A detached copy of the merged configuration (snapshots, UI)."""
        return copy.deepcopy(self._values)
