"""One command to run before every league match (T-2126).

    uv run python scripts/pre_match_smoke.py

Checks the things that have actually broken, in the order they would bite:
configuration, the goldens that prove our crypto still matches the reference,
our own self-play sanity, and the readiness checklist. Exits non-zero on the
first category that fails, so it can gate a match from a shell script.

Deliberately fast — a check nobody runs because it takes ten minutes is not a
check. The slow, exhaustive version is `scripts/check_all.py`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def console_script() -> str:
    """This repo's console-script name, read rather than hardcoded.

    The file is byte-identical in both repos, so it cannot name `najamjad-cop`
    or `najamjad-thief`. Reading it from `pyproject.toml` keeps the checks
    running the *installed entry point* — the thing a grader and an operator
    actually invoke — instead of reaching past it into a module.
    """
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return next(iter(manifest["project"]["scripts"]))


CLI = console_script()
GOLDEN = ROOT / "tests/goldens/artifacts/log_segal-police-team-vs-segal-thief-team_g01.json"
TAMPERED = ROOT / "tests/goldens/artifacts/log_tampered_step7.json"

# (label, argv, the exit code that means "healthy")
CHECKS: list[tuple[str, list[str], int]] = [
    ("config loads and validates", ["uv", "run", "python", "-c",
        "from pathlib import Path;from najamjad_agent.shared.config import ConfigManager;"
        "from najamjad_agent.sdk.bootstrap import default_config_path;"
        "ConfigManager.load(default_config_path(), shared_config=Path('config/game.json'))"], 0),
    ("golden log verifies (crypto matches the reference)",
        ["uv", "run", CLI, "replay", str(GOLDEN)], 0),
    ("tampered log is caught (the audit still bites)",
        ["uv", "run", CLI, "replay", str(TAMPERED)], 1),
    ("interop contract holds",
        ["uv", "run", "pytest", "tests/integration/test_interop_contract.py", "-q", "--no-cov"], 0),
    ("we still play a clean audited game",
        ["uv", "run", "pytest", "tests/integration/test_match_series.py", "-q", "--no-cov"], 0),
    ("core is identical to the sibling repo",
        ["uv", "run", "python", "scripts/sync_core.py", "../najamjad-thief"], 0),
]


def run(label: str, argv: list[str], expected: int) -> tuple[bool, float, str]:
    """Run one check; return whether it met its expected exit code."""
    started = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-8:])
    return result.returncode == expected, time.monotonic() - started, tail


def main(argv: list[str] | None = None) -> int:
    """Run every check and print one verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true",
                        help="also run the match-day readiness checklist (needs an opponent URL)")
    args = parser.parse_args(argv)

    checks = list(CHECKS)
    if args.preflight:
        checks.append(("match-day preflight",
                       ["uv", "run", CLI, "preflight"], 0))

    failures = []
    for label, command, expected in checks:
        ok, elapsed, tail = run(label, command, expected)
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:48} ({elapsed:4.1f}s)")
        if not ok:
            failures.append(label)
            print("\n".join(f"        {line}" for line in tail.splitlines()))

    print("-" * 68)
    if failures:
        print(f"NOT MATCH READY — {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("MATCH READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
