"""Replay an opponent's revealed records and report every rule breach in them.

    uv run python scripts/audit_opponent.py --team vibecode
    uv run python scripts/audit_opponent.py --archive matches/<dir>

`FairPlayMonitor` runs during play, on the messages a peer sends us — and the
protocol seals positions, so a peer sends none. Its movement and Barrier-Law
checks therefore have nothing to read while a match is on: they are live code
that cannot fire on live input. The place they *can* fire is here, after the
audit, when the reveal finally puts the opponent's true cell on every step.

That is the whole reason this exists as a separate tool rather than a stricter
setting. Run it on an archive before agreeing to play a team again, and on the
fresh archive afterwards.

**What a reveal can and cannot settle.** Their sealed records carry `position`,
`move` and `barrier_placed`, so movement legality, the Barrier Law, the barrier
budget and step order are all checkable from the archive alone. They do *not*
carry `smell_grid`, `capture_claim`, `hint` or response times — a peer's commit
preimage holds what that peer chose to seal, and the league's default
`smell_binding: none` puts no grid in a record by design. Those four can only be
checked against what arrived **on the wire**, which is why `FrameLog` keeps
their frames, their hints and their claims as sent, and why `verify_trail`
compares them at the audit. For a series played before that recording existed,
this tool reports them as *not checkable* rather than as clean — the difference
between "we looked and agreed" and "there was nothing to look at" is the whole
point of an audit.

Observational, like everything else that watches an opponent. It prints
evidence: the step, and the two facts that conflict. Deciding a match on our own
accusation is the contradiction rules 33-35 void both teams for.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from najamjad_agent.domain.board import Board  # noqa: E402
from najamjad_agent.domain.fair_play import FairPlayMonitor  # noqa: E402
from najamjad_agent.domain.params import GameParams  # noqa: E402

#: Fields a peer's sealed record may simply not contain. Their absence is not a
#: clean bill of health, and saying so out loud is the point.
WIRE_ONLY = ("smell_grid", "capture_claim", "hint", "response_seconds")


#: Their step-0 `role` as they spell it, mapped to the card's key.
_ROLE_KEYS = {"police": "cop", "cop": "cop", "thief": "thief"}


def declared_commits(logs: list[Path], group: str) -> dict[str, str]:
    """The commit their step-0 declares, **per role they played**.

    Per role, not per series, because a role-split opponent is two processes
    with two checkouts. vibecode's archive proves it: their thief declared
    `ee853d79…` and their cop `1ab98583…` in the same six sub-games. Reading one
    commit for the series would report one of them as the other's, which is the
    same class of wrong answer as reading our own self-play log for theirs.
    """
    found: dict[str, str] = {}
    for path in logs:
        log = json.loads(path.read_text(encoding="utf-8"))
        if group and group not in str(log.get("game_id", "")):
            continue
        for record in log.get("opponent_records", []):
            payload = record.get("payload", {})
            key = _ROLE_KEYS.get(str(payload.get("role", "")).lower())
            if key and payload.get("github_commit"):
                found.setdefault(key, str(payload["github_commit"]))
    return found


def check_commit(card: dict, declared: dict[str, str], role_key: str) -> str | None:
    """Compare what they *told* us they were playing against what they declared.

    Their commit reaches the result artifact on its own — it rides in their
    step-0 record and `peer_declaration.peer_facts` reads it — so nothing here
    is needed to *file* a match. What is missing without this is a control: a
    hash a team sends in a message is only worth having if something compares it
    to the hash their agent actually declares, and until now the messaged value
    sat in a `notes` string that no code ever read.

    A mismatch is a rule-53 finding and is reported as evidence, never acted on.
    The likeliest cause by far is an honest team pushing a fix and forgetting to
    resend, which is a message to them and not an accusation.

    An empty expectation is skipped rather than failed. We usually do not have
    one, and a check that goes red for the normal case teaches people to ignore
    it — the same reason `counted_ledger_check` reports instead of repairing.
    """
    expected = str((card.get("armed_commits") or {}).get(role_key, "")).strip()
    actual = declared.get(role_key, "")
    if not expected:
        return f"none on record; they declared {actual or 'nothing'}"
    if not actual:
        return f"they declared none; we were told {expected}"
    if expected != actual:
        return (f"MISMATCH — told {expected}, declared {actual} (rule 53). "
                "Most likely they pushed after messaging us; ask before assuming.")
    return f"matches what they told us ({actual[:12]}…)"


def _records(log: dict) -> list[dict]:
    """Their revealed step records, in step order, step 0 dropped."""
    steps = {}
    for record in log.get("opponent_records", []):
        payload = record.get("payload", {})
        if isinstance(payload.get("step"), int) and payload.get("position"):
            steps[payload["step"]] = payload
    return [steps[key] for key in sorted(steps)]


def audit_game(config: dict, log: dict) -> dict:
    """Replay one mini-game's reveals through the fair-play rules."""
    params = GameParams.from_config(config)
    monitor = FairPlayMonitor(max_barriers=params.max_barriers)
    board = Board(params)
    records = _records(log)

    for payload in records:
        # The board must carry the walls they have already declared, or
        # `through-barrier` can never fire and `_check_move` is half a check.
        findings = monitor.observe(board, payload["step"], payload)
        del findings
        wall = payload.get("barrier_placed")
        if isinstance(wall, list) and len(wall) == 2:
            cell = (int(wall[0]), int(wall[1]))
            if board.in_bounds(cell):
                board = board.with_barrier(cell)

    present = {field for payload in records for field in WIRE_ONLY if field in payload}
    return {
        "steps": len(records),
        "violations": [finding.as_dict() for finding in monitor.findings],
        "barriers": monitor.barriers_seen,
        "not_checkable": sorted(set(WIRE_ONLY) - present),
        "audit_passed": log.get("summary", {}).get("audit", {}).get("passed"),
    }


def audit_archive(directory: Path, card: dict | None = None, current: bool = True) -> int:
    """Report every mini-game in one archived series.

    `current` says whether this directory is the latest series against them, and
    it decides only how the commit line reads: the armed pair on the card is what
    they say they will play *next*, so checking it against an older archive is a
    category error rather than a finding.
    """
    logs = sorted(directory.glob("log_*.json"))
    if not logs:
        print(f"no logs in {directory}")
        return 1
    print(f"\n=== {directory.name}")
    if card is not None:
        # Once per series per role, not per mini-game: a step-0 declaration is a
        # property of the process they ran, and repeating it six times would
        # bury the findings that really are per-game.
        declared = declared_commits(logs, str(card.get("group_id", "")))
        for role in ("cop", "thief"):
            if current:
                print(f"  their {role:<5} commit: {check_commit(card, declared, role)}")
            else:
                # An older archive was played on whatever they were running
                # then, so comparing it against the pair they have *since* armed
                # reports a rule-53 mismatch for a team that did nothing wrong.
                # A check that cries wolf on every historical directory is one
                # an operator learns to scroll past.
                print(f"  their {role:<5} commit (as played): "
                      f"{declared.get(role) or 'not declared'}")
    total = 0
    for log_path in logs:
        log = json.loads(log_path.read_text(encoding="utf-8"))
        config_path = directory / log_path.name.replace("log_", "config_")
        if not config_path.exists():
            print(f"  {log_path.stem}: no config beside it — skipped")
            continue
        report = audit_game(json.loads(config_path.read_text(encoding="utf-8")), log)
        if not report["steps"]:
            print(f"  {log_path.stem}: no revealed records (sub-game never played)")
            continue
        verdict = "CLEAN" if not report["violations"] else f"{len(report['violations'])} VIOLATION(S)"
        print(f"  {log_path.stem}: {report['steps']} revealed steps, "
              f"{report['barriers']} barriers — {verdict}")
        for finding in report["violations"]:
            print(f"      step {finding['step']:>3}  {finding['rule']}: {finding['detail']}")
        total += len(report["violations"])
        if report["not_checkable"]:
            print(f"      not checkable from their reveals: "
                  f"{', '.join(report['not_checkable'])} — needs wire frames from a live match")
    print(f"  --- {total} violation(s) across the series")
    return 0


def _stamp(directory: Path) -> str:
    """The archive's trailing timestamp, or empty for a hand-named directory."""
    tail = directory.name.rsplit("-", 1)[-1]
    return tail if tail.endswith("Z") and tail[:8].isdigit() else ""


def _card(team: str) -> dict | None:
    """Their card, when one exists. A missing card is not an audit failure."""
    from najamjad_agent.shared.opponents import OpponentError, load_opponent

    try:
        return load_opponent(team)
    except OpponentError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", help="audit every archive whose name contains this")
    parser.add_argument("--archive", help="audit one archive directory")
    args = parser.parse_args()

    card = _card(args.team) if args.team else None
    if args.archive:
        return audit_archive(Path(args.archive), card)
    if not args.team:
        parser.error("pass --team or --archive")
    found = sorted({Path(path) for repo in ("najamjad-cop", "najamjad-thief")
                    for path in glob.glob(str(ROOT.parent / repo / "matches" / f"*{args.team}*"))
                    if Path(path).is_dir()})
    if not found:
        print(f"no archives matching {args.team!r}")
        return 1
    # By the trailing `-YYYYMMDDTHHMMSSZ`, not by path: the two repos hold
    # copies of the same series and the name prefixes differ, so a plain sort
    # made "newest" mean "last alphabetically" and pointed the commit check at
    # an older archive.
    newest = max(found, key=_stamp) if found else None
    for directory in found:
        audit_archive(directory, card, current=directory == newest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
