"""Fixtures for testing the repo's CI gate scripts.

The scripts live outside the package (in `scripts/`), so they are loaded by
file path; this keeps them runnable via `uv run python scripts/<name>.py`
without packaging gymnastics.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def load_script():
    """Return a loader that imports a script module from `scripts/` by name."""

    def _load(name: str) -> ModuleType:
        path = REPO_ROOT / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load
