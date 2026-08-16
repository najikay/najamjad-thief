"""Make both repos declare the same counted-match count (rules 37-38).

    uv run python scripts/reconcile_counted.py ../najamjad-thief
    uv run python scripts/reconcile_counted.py ../najamjad-thief --apply

The ledger is written at settlement by whichever repo played the series, and a
series is played from **one** repo — the one whose role we open on. So counted
#1 (uoh-ay26, we opened as thief) landed only in `najamjad-thief`, counted #2
(imreeyal, thief again) only in `najamjad-thief`, and `najamjad-cop` still
declared **1** on 2026-08-14 with a truth of 2.

That is not cosmetic. `counted_games_played` goes out in every handshake, rule
38 judges it on *mutual consistency between the two teams' files*, and a false
declaration found at project review disqualifies the team. Opening the vibecode
series as cop would have told them we had played one counted match while
imreeyal's filed artifact says two.

**Nothing here types a number.** Every entry it copies was written by
`CountedGames.record` at a real settlement, in the other repo, and is moved
across by the same API. The merge is by `game_uid`, and each uid is checked
against the archives before it is accepted: a counted match with no artifact in
`matches/` is refused and reported, because the one thing worse than an
inconsistent count is a confident wrong one.

Run it after every counted series, from either repo. `--apply` writes; without
it, the tool only reports.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from najamjad_agent.negotiation.counted_games import (  # noqa: E402
    DEFAULT_PATH,
    CountedGames,
)


def _evidence(repos: list[Path], game_uid: str) -> bool:
    """True when some archived artifact carries this uid in either repo."""
    if not game_uid:
        return False
    for repo in repos:
        for path in glob.glob(str(repo / "matches" / "**" / "*.json"), recursive=True):
            try:
                if game_uid in Path(path).read_text(encoding="utf-8"):
                    return True
            except OSError:
                continue
    return False


def reconcile(here: Path, sibling: Path, apply: bool) -> int:
    """Union both ledgers, refusing any entry the archives cannot corroborate."""
    repos = [here, sibling]
    trackers = {repo: CountedGames.load(repo / DEFAULT_PATH) for repo in repos}
    for repo, tracker in trackers.items():
        print(f"{repo.name}: {tracker.count} counted — {tracker.opponents}")

    merged: dict[str, dict] = {}
    for tracker in trackers.values():
        for entry in tracker.history:
            uid = str(entry.get("game_uid", ""))
            merged.setdefault(uid, entry)

    refused = [uid for uid in merged if not _evidence(repos, uid)]
    for uid in refused:
        print(f"  REFUSED {merged[uid].get('opponent')} ({uid or 'no uid'}): "
              "no archived artifact carries this game_uid")
        del merged[uid]

    changed = 0
    for repo, tracker in trackers.items():
        wanted = sorted(merged.values(), key=lambda entry: str(entry.get("at", "")))
        for entry in wanted:
            opponent = str(entry.get("opponent", ""))
            if tracker.already_played(opponent):
                continue
            print(f"  {repo.name}: + {opponent} ({entry.get('at')}) "
                  f"[written by the other repo at settlement]")
            changed += 1
            if apply:
                tracker.record(opponent, str(entry.get("game_uid", "")),
                               str(entry.get("at", "")))
    if not changed:
        print("both ledgers already agree — nothing to do")
        return 0
    if not apply:
        print(f"\n{changed} entry/entries would be copied. Re-run with --apply to write.")
        return 0
    for repo, tracker in trackers.items():
        print(f"{repo.name}: now declares {tracker.count} — {tracker.opponents}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sibling", help="path to the sibling repository root")
    parser.add_argument("--apply", action="store_true", help="write instead of only reporting")
    args = parser.parse_args()
    return reconcile(ROOT, Path(args.sibling).resolve(), args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
