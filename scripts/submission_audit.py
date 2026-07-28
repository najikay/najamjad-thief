"""The mechanical half of the submission checklist (T-2401, T-2403, T-2406, T-2409).

    uv run python scripts/submission_audit.py

Everything a machine can check before submitting: mandated files present,
versions consistent, links well-formed, content deliverables produced, no secret
tracked. It prints one verdict and exits non-zero on any failure, so it can gate
a tag.

It deliberately does **not** claim to check the things it cannot: whether the
Moodle form was submitted, whether the repos are visible to the lecturer, or
whether a link resolves on the public internet. Those are printed as prompts.
A checklist that pretends to have verified something it did not is worse than no
checklist — that is how a submission gets marked down for a detail everyone
believed was covered.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANDATED = [
    "README.md", "CONTRIBUTING.md", "LICENSE", "uv.lock", ".env-example",
    "docs/PRD.md", "docs/PLAN.md", "docs/TODO.md", "docs/CORE_SYNC.md",
    "docs/RUNBOOK.md", "docs/SECURITY.md", "docs/UX.md", "docs/CONFIG.md",
    "docs/CI.md", "docs/EXTENDING.md", "docs/ISO25010.md", "docs/edge-cases.md",
    "docs/PROMPT_BOOK.md", "docs/TOKEN_BUDGET.md", "docs/OPEN_ITEMS.md",
    "config/game.json", "config/setup.json", "config/rate_limits.json",
    "config/logging_config.json", "notebooks/analysis.ipynb",
]
DELIVERABLES = {
    "prompt book": "docs/PROMPT_BOOK.md",
    "analysis notebook": "notebooks/analysis.ipynb",
    "C4 context diagram": "assets/c4-context.png",
    "C4 container diagram": "assets/c4-container.png",
    "C4 component diagram": "assets/c4-component.png",
    "deployment diagram": "assets/deployment.png",
    "UML game FSM": "assets/uml-game-fsm.png",
    "UML turn sequence": "assets/uml-turn-sequence.png",
    "UML match lifecycle": "assets/uml-match-lifecycle.png",
    "dashboard screenshot": "assets/dashboard-live.png",
    "replay verified screenshot": "assets/replay-verified-ok.png",
    "replay tampered screenshot": "assets/replay-tampered.png",
    "ISO 25010 mapping": "docs/ISO25010.md",
    "extension docs": "docs/EXTENDING.md",
}
HUMAN_ONLY = [
    "both repos public, or shared with rmisegal@gmail.com (T-2405)",
    "Moodle template filled per member, exported to PDF, fields unmoved (T-2412/T-2414)",
    "each member submitted separately with team code NajAmjad (T-2415)",
    "every counted match has BOTH sides' reports sent and non-contradictory (T-2416)",
]


def missing_files(names: list[str]) -> list[str]:
    """Which of these do not exist."""
    return [name for name in names if not (ROOT / name).exists()]


def version_report() -> tuple[bool, list[str]]:
    """Every shipped version string should agree."""
    found: dict[str, str] = {}
    # Named sources, each of which MUST yield a version. A source that silently
    # yields nothing is how an audit reports agreement between two files while a
    # third disagrees — the failure mode this whole script exists to avoid.
    sources = {
        "version.py": (ROOT / "src/najamjad_agent/shared/version.py",
                       r'CODE_VERSION\s*=\s*"([^"]+)"'),
        "pyproject.toml": (ROOT / "pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "config/game.json": (ROOT / "config/game.json", r'"schema_version"\s*:\s*"([^"]+)"'),
    }
    for label, (path, pattern) in sources.items():
        if not path.exists():
            found[label] = "MISSING FILE"
            continue
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
        found[label] = match.group(1) if match else "NOT FOUND"
    for name in ("config/setup.json", "config/rate_limits.json", "config/logging_config.json"):
        path = ROOT / name
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        value = raw.get("version") or raw.get("_config_version")
        inner = raw.get("rate_limits", {})
        found[name] = str(inner.get("version") if isinstance(inner, dict) and inner else value)
    # `1` is dictConfig's own schema version and `1.3` the wire schema the
    # reference fixes; neither is ours to keep in step with the code version.
    ignored = {None, "1", "None", "1.3"}
    unresolved = [name for name, value in found.items() if value in ("MISSING FILE", "NOT FOUND")]
    distinct = {value for value in found.values() if value not in ignored | set(unresolved)}
    if unresolved:
        distinct.add("unresolved")
    lines = [f"    {name}: {value}" for name, value in sorted(found.items())]
    return len(distinct) <= 1, lines


def broken_links() -> list[str]:
    """Markdown links pointing at files that are not there."""
    broken: list[str] = []
    for document in ROOT.glob("docs/*.md"):
        text = document.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r"\]\((?!https?://|#)([^)\s]+)\)", text):
            candidate = (document.parent / target).resolve()
            if not candidate.exists() and not (ROOT / target).exists():
                broken.append(f"{document.name} -> {target}")
    return broken


def tracked_secrets() -> list[str]:
    """Anything secret that git knows about."""
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                            check=False)
    forbidden = (".env", "credentials.json", "token.json")
    return [
        line for line in result.stdout.splitlines()
        if Path(line).name in forbidden or Path(line).suffix in {".pem", ".key"}
    ]


def main() -> int:
    """Run every mechanical check and print one verdict."""
    failures: list[str] = []
    print("submission audit\n")

    for label, names in (("mandated files", MANDATED), ("deliverables", list(DELIVERABLES.values()))):
        absent = missing_files(names)
        print(f"  {'ok  ' if not absent else 'FAIL'}  {label} ({len(names) - len(absent)}/{len(names)})")
        for name in absent:
            print(f"          missing: {name}")
        if absent:
            failures.append(label)

    consistent, lines = version_report()
    print(f"  {'ok  ' if consistent else 'FAIL'}  versions agree")
    for line in lines:
        print(line)
    if not consistent:
        failures.append("versions")

    broken = broken_links()
    print(f"  {'ok  ' if not broken else 'FAIL'}  documentation links ({len(broken)} broken)")
    for item in broken[:8]:
        print(f"          {item}")
    if broken:
        failures.append("links")

    secrets = tracked_secrets()
    print(f"  {'ok  ' if not secrets else 'FAIL'}  no secret is tracked")
    for item in secrets:
        print(f"          TRACKED SECRET: {item}")
    if secrets:
        failures.append("secrets")

    print("\n  cannot be checked from here — a human must confirm each:")
    for item in HUMAN_ONLY:
        print(f"    [ ] {item}")

    print("-" * 70)
    if failures:
        print(f"SUBMISSION AUDIT FAILED — {', '.join(failures)}")
        return 1
    print("SUBMISSION AUDIT PASSED — now confirm the four above by hand")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
