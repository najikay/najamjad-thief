"""Mirror the shared core between the cop and thief repositories (PLAN ADR-002).

Why: submission requires two standalone repos, but the core package must not
drift. This tool copies every manifest-listed path from the current repo to
its sibling (`--push`) or verifies byte-identity (`--check`, used by CI).
Role-specific paths (README, configs, pyproject name) are NOT in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import re
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
# Only the lines naming this repo may differ between cop and thief: the project
# name, its description, and its console-script entry point. Every other line —
# dependencies, dev dependencies, ruff/pytest/coverage config — must match, or
# the repos are no longer held to the same standard.
#
# The entry point is here because it is easy to forget it names the repo: an
# earlier version of this pattern mirrored it verbatim, and the thief repo
# ended up shipping a `najamjad-cop` command that could not be launched.
ROLE_SPECIFIC = re.compile(r"^\s*(name|description|najamjad-\w+)\s*=")


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


def _shared_lines(path: Path) -> list[str]:
    """Every pyproject line that must be identical across the two repos.

    Only `name` and `description` are legitimately role-specific. Everything
    else — runtime dependencies, dev dependencies, and the whole `[tool.*]`
    half — has to match, because a difference there means the two repos are no
    longer being held to the same standard. A dev dependency that exists in one
    repo and not the other is the quiet version of that: a test imports it,
    passes where it was declared, and fails in the twin for reasons that look
    unrelated to the change that exposed it.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if not ROLE_SPECIFIC.match(line)]


def check_tooling(source: Path, sibling: Path, push: bool) -> int:
    """Compare (or copy) the shared pyproject config; return 1 on drift."""
    ours, theirs = source / "pyproject.toml", sibling / "pyproject.toml"
    if not theirs.exists() or _shared_lines(ours) == _shared_lines(theirs):
        return 0
    if not push:
        print("DRIFT  pyproject.toml shared configuration")
        return 1
    # Keep the twin's own name/description, take every other line from ours.
    # Matched by position rather than by field name: `name =` is not unique in
    # a TOML file, so keying on it would let a `[tool.*]` entry overwrite the
    # project's own identity.
    preserved = iter(
        line for line in theirs.read_text(encoding="utf-8").splitlines() if ROLE_SPECIFIC.match(line)
    )
    merged = [
        next(preserved, line) if ROLE_SPECIFIC.match(line) else line
        for line in ours.read_text(encoding="utf-8").splitlines()
    ]
    theirs.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print("SYNCED pyproject.toml shared configuration")
    return 1


def orphans(source: Path, sibling: Path) -> list[Path]:
    """Manifest files the sibling still has and the source no longer does.

    Copying alone is not mirroring. A renamed or deleted file stays behind in
    the twin forever, and the stale copy is not inert: two test modules with the
    same basename collide under pytest, so a rename in one repo broke the
    other's entire suite while every file it *did* copy was byte-identical.
    """
    ours = {file.relative_to(source) for entry in MANIFEST for file in _files_under(source, entry)}
    theirs = {
        file.relative_to(sibling) for entry in MANIFEST for file in _files_under(sibling, entry)
    }
    return sorted(theirs - ours)


def run(source: Path, sibling: Path, push: bool) -> int:
    """Compare (or copy) all manifest files; return count of drifted files."""
    drift = check_tooling(source, sibling, push)
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
    for stale in orphans(source, sibling):
        drift += 1
        if push:
            (sibling / stale).unlink()
            print(f"REMOVED {stale}")
        else:
            print(f"ORPHAN  {stale}")
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
