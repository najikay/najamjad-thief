"""Where the dashboard looks for past matches.

One module so the answer is the same for the web routes, the CLI and the
archive step. The paths come from `config/setup.json`; the group id from the
private config — neither is a literal here.
"""

from __future__ import annotations

from pathlib import Path

from ..shared.app_config import load_setup, setting


def history_roots() -> tuple[Path, ...]:
    """Both places a filed match can be found, live and archived."""
    setup = load_setup()
    return (
        Path(setting(setup, "paths.artifacts", "workspace/artifacts")),
        Path(setting(setup, "paths.matches", "matches")),
    )


def our_group(default: str = "najamjad") -> str:
    """Our group id, as the artifacts key their scores by."""
    from ..shared.config import ConfigManager
    from .bootstrap import default_config_path, shared_config_for

    try:
        role_dir = default_config_path()
        manager = ConfigManager.load(role_dir, shared_config=shared_config_for(role_dir))
        return str(manager.get("game.group_id", default))
    except Exception:  # noqa: BLE001 - a dashboard must not fail on config
        return default
