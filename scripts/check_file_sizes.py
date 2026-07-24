"""CI gate: enforce the course per-file size rule (guidelines §3.2).

Why: every source AND test file may hold at most 150 lines of code, where
blank lines, comment lines, and docstrings do not count. We additionally warn
at 120 (internal design budget, PLAN §1.3) so refactors happen before the
hard cap is ever at risk. Split files, never compress (guidelines §3.2).
"""

from __future__ import annotations

import ast
import sys
import tokenize
from pathlib import Path

HARD_CAP = 150
WARN_CAP = 120
SCANNED_DIRS = ("src", "tests", "scripts")


def _docstring_lines(tree: ast.AST) -> set[int]:
    """Collect line numbers occupied by module/class/function docstrings."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not (node.body and isinstance(node.body[0], ast.Expr)):
            continue
        value = node.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            lines.update(range(value.lineno, (value.end_lineno or value.lineno) + 1))
    return lines


def _comment_lines(path: Path) -> set[int]:
    """Collect line numbers whose only content is a comment."""
    lines: set[int] = set()
    with tokenize.open(path) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.COMMENT and token.line.strip().startswith("#"):
                lines.add(token.start[0])
    return lines


def count_code_lines(path: Path) -> int:
    """Count lines that are neither blank, comment-only, nor docstring."""
    text = path.read_text(encoding="utf-8")
    skip = _docstring_lines(ast.parse(text)) | _comment_lines(path)
    total = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() and number not in skip:
            total += 1
    return total


def main() -> int:
    """Scan the repo; return non-zero if any file breaks the hard cap."""
    root = Path(__file__).resolve().parent.parent
    failures: list[str] = []
    for directory in SCANNED_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            count = count_code_lines(path)
            relative = path.relative_to(root)
            if count > HARD_CAP:
                failures.append(f"FAIL {relative}: {count} code lines (cap {HARD_CAP})")
            elif count > WARN_CAP:
                print(f"WARN {relative}: {count} code lines (budget {WARN_CAP})")
    for failure in failures:
        print(failure)
    print("file-size gate:", "FAILED" if failures else "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
