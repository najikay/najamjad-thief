"""Match-day switches, so nothing is hand-edited under time pressure.

Three things change between a warm-up and a counted match, and getting any one
wrong is a zero rather than a loss:

* the opponent card — their URL and the `group_id` their handshake declares,
* `email.mode`, which ships as `draft` and must be `send` for a counted run,
* the artifacts directory, which is keyed by `game_id` and therefore silently
  overwritten when the same pair plays twice (rule 52 permits exactly that).

Doing those by hand at 20:00 is how the draft trap nearly shipped. Each is one
subcommand here, applied to **both** repos, and every one prints what it did.

    uv run python scripts/match_day.py card --team rival \\
        --url https://rival.example.com/mcp --group-id rival-team
    uv run python scripts/match_day.py archive --team rival
    uv run python scripts/match_day.py counted        # or: practice
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPOS = (HERE, HERE.parent / ("najamjad-thief" if HERE.name == "najamjad-cop" else "najamjad-cop"))
ROLE_CONFIG = {"najamjad-cop": "police", "najamjad-thief": "thief"}

CARD = '''# {name}
#
# Both values come from THEM. `group_id` must equal what their handshake
# declares, or the filer's rename never fires and our emitted report is keyed
# by a placeholder instead of their name.
url      = "{url}"
group_id = "{group_id}"
name     = "{name}"
notes    = "{notes}"
'''


def write_card(team: str, url: str, group_id: str, notes: str) -> None:
    """Write one opponent card into both repos, under the same name.

    The same name in both is deliberate: the cop dialling `rival` and the thief
    dialling something else means remembering which half you are running, which
    has already failed once with `no opponent card`.
    """
    body = CARD.format(url=url, group_id=group_id, name=team, notes=notes)
    for repo in REPOS:
        target = repo / "opponents" / f"{team}.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        print(f"  wrote {target.relative_to(repo.parent)}")


def set_mode(mode: str) -> None:
    """Flip `email.mode` in both repos' private config.

    `send` is what a counted match needs; `draft` is the safe default that
    would otherwise leave a graded report sitting in a drafts folder while
    everything looked successful.
    """
    for repo in REPOS:
        role = ROLE_CONFIG.get(repo.name)
        if role is None:
            continue
        path = repo / "config" / role / "game.toml"
        text = path.read_text(encoding="utf-8")
        updated = re.sub(r'^mode = "\w+"', f'mode = "{mode}"', text, count=1, flags=re.M)
        path.write_text(updated, encoding="utf-8")
        print(f"  {path.relative_to(repo.parent)}: email.mode = {mode!r}")


def archive(team: str) -> None:
    """Move the current artifacts aside so the next match cannot overwrite them.

    `game_id` is derived from the two group ids and the terms, so the same pair
    on the same terms produces identical filenames and an identical `game_uid`
    every time. A warm-up followed by a counted match against the same team
    therefore overwrites the first, and both reports carry one uid.
    """
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    for repo in REPOS:
        source = repo / "workspace" / "artifacts"
        if not source.is_dir() or not any(source.iterdir()):
            print(f"  {repo.name}: nothing to archive")
            continue
        destination = repo / "matches" / f"{team}-{stamp}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        source.mkdir(parents=True, exist_ok=True)
        print(f"  {repo.name}: artifacts -> {destination.relative_to(repo)}")


def main() -> int:
    """Route one subcommand; every path prints what it changed."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    card = sub.add_parser("card", help="write an opponent card into both repos")
    card.add_argument("--team", required=True, help="card name, e.g. 'rival'")
    card.add_argument("--url", required=True, help="their MCP endpoint")
    card.add_argument("--group-id", required=True, help="the id THEIR handshake declares")
    card.add_argument("--notes", default="", help="anything worth remembering")

    keep = sub.add_parser("archive", help="move artifacts aside before a rerun")
    keep.add_argument("--team", required=True, help="what to label the archive")

    sub.add_parser("counted", help="arm a counted match (email.mode = send)")
    sub.add_parser("practice", help="restore the safe default (email.mode = draft)")

    args = parser.parse_args()
    if args.command == "card":
        write_card(args.team, args.url, args.group_id, args.notes)
        print("\nNext: uv run najamjad-cop preflight --opponent " + args.team)
    elif args.command == "archive":
        archive(args.team)
    else:
        set_mode("send" if args.command == "counted" else "draft")
        print("\nNext: preflight will refuse a counted run until this reads 'send'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
