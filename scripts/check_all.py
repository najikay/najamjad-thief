"""Run every CI gate locally and print one unambiguous verdict.

Why this exists: the gates used to be chained by hand on the command line and
read off the tail of a long output. That is how a pyright failure once got
reported as "clean" — the summary line had scrolled past, and a commit message
claimed something nobody had actually checked. A single command with a single
verdict at the end removes the judgement call.

Mirrors `.github/workflows/ci.yml`; if a gate is added there, add it here.

    uv run python scripts/check_all.py          # everything
    uv run python scripts/check_all.py --fast   # skip the slow test suite
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

Gate = tuple[str, list[str], bool]
GATES: list[Gate] = [
    ("ruff", ["uv", "run", "ruff", "check", "."], False),
    ("file sizes", ["uv", "run", "python", "scripts/check_file_sizes.py"], False),
    ("repo rules", ["uv", "run", "python", "scripts/check_repo_rules.py"], False),
    ("pyright", ["uv", "run", "pyright"], False),
    ("tests", ["uv", "run", "pytest", "tests/", "-q"], True),
]


def run(name: str, command: list[str]) -> tuple[bool, float, str]:
    """Run one gate, returning whether it passed, how long it took, and its tail."""
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    elapsed = time.monotonic() - started
    output = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode == 0, elapsed, "\n".join(output[-15:])


def main(argv: list[str] | None = None) -> int:
    """Run each gate in turn and report a single PASS/FAIL verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="skip the slow test suite")
    args = parser.parse_args(argv)

    gates = [gate for gate in GATES if not (args.fast and gate[2])]
    failures: list[str] = []
    for name, command, _slow in gates:
        print(f"→ {name} …", flush=True)
        passed, elapsed, tail = run(name, command)
        print(f"  {'PASS' if passed else 'FAIL'} ({elapsed:.0f}s)")
        if not passed:
            failures.append(name)
            print(f"\n{tail}\n")

    print("-" * 60)
    if failures:
        print(f"GATES FAILED: {', '.join(failures)}")
        return 1
    skipped = " (test suite skipped)" if args.fast else ""
    print(f"ALL GATES PASSED{skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
