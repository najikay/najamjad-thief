"""CI gate: repo hygiene rules that ruff cannot express.

Why: three guideline/book rules are enforced by scanning text, not linting —
(1) uv-only tooling: no `pip install`, and no bare `python -m` outside
    `uv run` (guidelines §8.4). In markdown, only fenced code blocks count as
    executable — prose that *describes* the prohibition is not a violation;
    quoted third-party commands inside fences carry an inline marker;
(2) no silent exception swallowing (`except: pass`) — A6's worst bug class
    (PLAN ADR-008);
(3) no secret material committed (guidelines §7.4; book rules 39-40).
This file itself defines the patterns and is excluded from its own scan.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

QUOTE_MARKER = "third-party-quote-ok"
# A file whose header declares this marker holds deliberately planted bad
# patterns (the gate's own test fixtures). Content scanning is skipped for it;
# filename/secret-file rules still apply. Kept narrow and header-only so the
# escape hatch cannot be hidden deep inside a real module.
FIXTURE_MARKER = "repo-rules-gate-fixtures"
FIXTURE_HEADER_LINES = 15
# `uv run python -m mod` is uv-only tooling and is what the rule wants; only a
# bare interpreter invocation escapes the locked environment. `pip install`
# stays forbidden either way, so `uv run python -m pip install` is still caught.
UV_ONLY = re.compile(r"\bpip3? install\b|(?<!uv run )\bpython3? -m\b")
SILENT_EXCEPT = re.compile(r"except[^:\n]*:\s*(?:pass|\.\.\.)\s*$", re.MULTILINE)
SECRET_HINTS = re.compile(r"sk-ant-api|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|AIzaSy[\w-]{30}")
FORBIDDEN_TRACKED = ("credentials.json", "token.json", ".env")
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".sh"}


def _tracked_files(root: Path) -> list[Path]:
    """Files git knows about, plus new ones it does not know about *yet*.

    Scanning only tracked files makes this gate blind to exactly the file most
    likely to break it: a brand-new one. It passes locally, gets committed,
    becomes tracked, and fails in CI — which is precisely how a test file full
    of deliberately forbidden patterns reached a red pipeline having been green
    on the machine that wrote it.

    `--others --exclude-standard` adds untracked files while still honouring
    `.gitignore`, so scratch files and the virtualenv stay out of it.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return [root / line for line in result.stdout.splitlines()]
    return [p for p in root.rglob("*") if p.is_file() and ".venv" not in p.parts]


def _scan(path: Path, root: Path) -> list[str]:
    """Return rule violations found in one file."""
    problems: list[str] = []
    relative = path.relative_to(root)
    if path.name in FORBIDDEN_TRACKED or path.suffix in {".pem", ".key"}:
        problems.append(f"SECRET-FILE {relative}: must never be committed")
        return problems
    if path.suffix not in TEXT_SUFFIXES or path.name == Path(__file__).name:
        return problems
    if not path.is_file():
        # `git ls-files --cached` lists files deleted in the working tree but
        # not yet staged. That is an ordinary state — `match_day.py archive`
        # moves artifacts out of `workspace/` — and it used to abort the whole
        # gate with a FileNotFoundError traceback instead of a verdict. Deleted
        # content cannot violate a content rule; the name rules above already
        # ran, so skipping here loses nothing.
        return problems
    text = path.read_text(encoding="utf-8", errors="replace")
    if FIXTURE_MARKER in "\n".join(text.splitlines()[:FIXTURE_HEADER_LINES]):
        return problems
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if path.suffix == ".md" and line.lstrip().startswith("```"):
            in_fence = not in_fence
        executable = in_fence if path.suffix == ".md" else True
        if executable and UV_ONLY.search(line) and QUOTE_MARKER not in line:
            problems.append(f"UV-ONLY {relative}:{number}: forbidden pip/python -m usage")
        if SECRET_HINTS.search(line):
            problems.append(f"SECRET-CONTENT {relative}:{number}: credential-like material")
    if path.suffix == ".py" and SILENT_EXCEPT.search(text):
        problems.append(f"SILENT-EXCEPT {relative}: bare pass/... exception handler")
    return problems


def main() -> int:
    """Scan tracked files; non-zero exit on any violation."""
    root = Path(__file__).resolve().parent.parent
    problems = [issue for path in _tracked_files(root) for issue in _scan(path, root)]
    for issue in problems:
        print(issue)
    print("repo-rules gate:", "FAILED" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
