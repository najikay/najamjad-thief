"""The mechanical half of the post-match checklist (T-2317).

    uv run python scripts/post_match.py --opponent segal --dir workspace/artifacts

Checks the things a tired human at 23:00 will otherwise skip: that every
artifact is present and parses, that every mini-game's log re-hashes to
`Verified OK`, that the games share one `game_uid`, and that the working tree is
clean so the `github_commit` we declared is the code we played (rule 53).

What it deliberately does **not** check is the half that needs a human: whether
our result agrees with theirs, and whether the report was actually sent. Those
are printed as prompts rather than silently assumed — a checklist that pretends
to verify something it cannot is worse than one that admits the gap.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from najamjad_agent.replay.verifier import verify_log  # noqa: E402

HUMAN_CHECKS = [
    "our result matches theirs (compare BEFORE sending — a disagreement voids the game for both)",
    "report emailed and the message id pasted into matches/opponents.md",
    "match config committed, and the declared github_commit opens on GitHub",
    "archive written and stored off this laptop",
    "incidents.md triaged: defect / adapter profile / accept",
]


def logs_in(directory: Path) -> list[Path]:
    """Every mini-game log in the artifacts directory, in game order."""
    return sorted(directory.glob("log_*.json"))


def check_logs(directory: Path) -> tuple[bool, list[str]]:
    """Re-hash every mini-game; return whether all verified, and the lines."""
    found = logs_in(directory)
    if not found:
        return False, [f"  FAIL  no log_*.json artifacts in {directory}"]

    lines, ok = [], True
    for path in found:
        try:
            result = verify_log(path)
        except Exception as error:  # a log we cannot even read is a failure
            lines.append(f"  FAIL  {path.name}: unreadable ({error})")
            ok = False
            continue
        lines.append(f"  {'ok  ' if not result.void else 'FAIL'}  {path.name}: {result.banner}")
        ok = ok and not result.void
    return ok, lines


def check_uid(directory: Path) -> tuple[bool, str]:
    """Every mini-game of one match must carry the same game_uid."""
    uids = set()
    for path in logs_in(directory):
        try:
            uids.add(json.loads(path.read_text(encoding="utf-8")).get("game_uid"))
        except (OSError, json.JSONDecodeError):
            return False, f"  FAIL  {path.name} could not be read for its game_uid"
    if len(uids) == 1:
        return True, f"  ok    all {len(logs_in(directory))} games share game_uid {uids.pop()}"
    return False, f"  FAIL  mini-games disagree about game_uid: {sorted(map(str, uids))}"


def check_clean_tree() -> tuple[bool, str]:
    """A dirty tree means the declared commit is not what we played."""
    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, "  FAIL  not a git repository — the github_commit cannot be verified"
    dirty = [line for line in result.stdout.splitlines() if line.strip()]
    if dirty:
        return False, f"  FAIL  {len(dirty)} uncommitted change(s) — declared commit is not exact"
    return True, "  ok    working tree clean; the declared github_commit is exact"


def main(argv: list[str] | None = None) -> int:
    """Run the mechanical checks and print the human ones."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opponent", default="<opponent>")
    parser.add_argument("--dir", type=Path, default=ROOT / "workspace/artifacts")
    args = parser.parse_args(argv)

    print(f"post-match verification — vs {args.opponent}\n")
    logs_ok, lines = check_logs(args.dir)
    for line in lines:
        print(line)
    uid_ok, uid_line = check_uid(args.dir)
    print(uid_line)
    tree_ok, tree_line = check_clean_tree()
    print(tree_line)

    print("\nstill needs a human — none of these can be checked from here:")
    for item in HUMAN_CHECKS:
        print(f"  [ ] {item}")

    print("-" * 70)
    if logs_ok and uid_ok and tree_ok:
        print("MECHANICAL CHECKS PASSED — now do the five above")
        return 0
    print("MECHANICAL CHECKS FAILED — do not file the report until this is understood")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
