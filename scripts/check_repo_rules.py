"""CI gate: repo hygiene rules that ruff cannot express.

Why: three guideline/book rules are enforced by scanning text, not linting —
(1) uv-only tooling: no `pip install` / `python -m` in any executable content
    (guidelines §8.4). In markdown, only fenced code blocks count as
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
UV_ONLY = re.compile(r"\bpip3? install\b|\bpython3? -m\b")
SILENT_EXCEPT = re.compile(r"except[^:\n]*:\s*(?:pass|\.\.\.)\s*$", re.MULTILINE)
SECRET_HINTS = re.compile(r"sk-ant-api|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|AIzaSy[\w-]{30}")
FORBIDDEN_TRACKED = ("credentials.json", "token.json", ".env")
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".sh"}


def _tracked_files(root: Path) -> list[Path]:
    """List git-tracked files, falling back to a filesystem walk pre-init."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=False
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
    text = path.read_text(encoding="utf-8", errors="replace")
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
