"""Mirror the shared core between the cop and thief repositories (PLAN ADR-002).

Why: submission requires two standalone repos, but the core package must not
drift. This tool copies every manifest-listed path from the current repo to
its sibling (`--push`) or verifies byte-identity (`--check`, used by CI).
Role-specific paths (README, configs, pyproject name) are NOT in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

MANIFEST = (
    "src/najamjad_agent",
    "tests",
    "scripts",
    "docs",
    ".github/workflows",
    ".gitignore",
    ".env-example",
    "LICENSE",
)
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def _files_under(base: Path, entry: str) -> list[Path]:
    """Expand one manifest entry into concrete files (skipping caches)."""
    target = base / entry
    if target.is_file():
        return [target]
    if not target.exists():
        return []
    return [p for p in sorted(target.rglob("*")) if p.is_file() and not SKIP_PARTS & set(p.parts)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source: Path, sibling: Path, push: bool) -> int:
    """Compare (or copy) all manifest files; return count of drifted files."""
    drift = 0
    for entry in MANIFEST:
        for file in _files_under(source, entry):
            relative = file.relative_to(source)
            twin = sibling / relative
            if twin.exists() and _digest(file) == _digest(twin):
                continue
            drift += 1
            if push:
                twin.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, twin)
                print(f"SYNCED {relative}")
            else:
                print(f"DRIFT  {relative}")
    return drift


def main() -> int:
    """CLI entry: `--push` to mirror, default `--check` verifies identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sibling", type=Path, help="path to the sibling repository root")
    parser.add_argument("--push", action="store_true", help="copy instead of only comparing")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    drift = run(source, args.sibling.resolve(), args.push)
    status = "SYNCED" if args.push else ("FAILED" if drift else "OK")
    print(f"core-manifest gate: {status} ({drift} file(s) differed)")
    return 0 if (args.push or drift == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
