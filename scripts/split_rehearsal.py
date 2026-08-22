"""Rehearse a role-split series end to end: four processes, two split teams.

    python scripts/split_rehearsal.py --games 6

`game.opening_role` splits our six windows across two processes (book Appendix
ה rule 1) and has never been played. Every other harness runs one process a
side, so none of them reaches `advance_to_ours`, the sibling merge, or a peer
that answers on two doors.

Our two real repos play the halves — the merge looks for its sibling beside it,
so they cannot be copies — against an opponent that is *also* split: two
processes under one temp working directory, running the cop repo's code with
their own workspace, group id and pair of doors.

Nothing tracked is touched: every config is a copy under the temp root, both
teams' `mcp_servers` name local ports, and `tunnel.hostname` is cleared.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("SPLIT_REHEARSAL_ROOT", "") or HERE.parent)
COP, THIEF = ROOT / "najamjad-cop", ROOT / "najamjad-thief"


def free_port() -> int:
    """A port the OS says is free right now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _set(text: str, key: str, value: str) -> str:
    """Replace `key = ...` on its own line, preserving everything else."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        hit = stripped.startswith(f"{key} ") or stripped.startswith(f"{key}=")
        out.append(f"{key} = {value}" if hit else line)
    return "\n".join(out) + "\n"


def both_roles(target: Path) -> Path:
    """A config tree holding *both* role directories, for a two-process team."""
    shutil.copytree(COP / "config", target)
    shutil.copytree(THIEF / "config/thief", target / "thief")
    return target


def configure(root: Path, role: str, mine: int, door: int, doors: dict[str, int]) -> Path:
    """Point one role's config at its own port and its counterpart's door."""
    toml = root / role / "game.toml"
    text = toml.read_text(encoding="utf-8")
    text = _set(text, "my_port", str(mine))
    text = _set(text, "opponent_url", f'"http://127.0.0.1:{door}/mcp"')
    text = _set(text, "hostname", '""')
    # Split mode declares `[game.mcp_servers]` verbatim, so in a local rehearsal
    # they must name the local doors — otherwise we advertise two tunnels that
    # are not running and only the peer's retarget guard saves the series.
    for name in ("cop", "thief"):
        text = text.replace(f"https://{name}.4laboratory.com/mcp",
                            f"http://127.0.0.1:{doors[name]}/mcp")
    toml.write_text(text, encoding="utf-8")
    return root / role


def terms(root: Path, games: int) -> None:
    """Agree the series length in the shared, signed terms."""
    shared = json.loads((root / "game.json").read_text(encoding="utf-8"))
    shared.setdefault("network_and_league", {})["num_games"] = games
    (root / "game.json").write_text(json.dumps(shared, indent=2), encoding="utf-8")


def launch(cwd: Path, config: Path, opens: str, log: Path, extra: list[str]) -> subprocess.Popen:
    """Start one process of one team, unbuffered so a kill leaves its account."""
    handle = log.open("w", encoding="utf-8")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(COP / "src")}
    env.pop("VIRTUAL_ENV", None)
    command = [
        str(COP / ".venv/bin/python"), "-u", "-m", "najamjad_agent.cli", "match",
        "--config", str(config), "--no-tunnel", "--no-dashboard", "--practice",
        "--opens", opens, *extra,
    ]
    return subprocess.Popen(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                            text=True, env=env)


def plan(work: Path, games: int, voice: list[str],
         opens: str = "thief") -> list[tuple[str, Path, Path, str, list[str]]]:
    """Four processes: our two repos, and an opponent split across two roles."""
    us = {"cop": free_port(), "thief": free_port()}
    them = {"cop": free_port(), "thief": free_port()}
    theirs = work / "opponent"
    (theirs / "workspace").mkdir(parents=True)
    # One config tree per team, both role directories in each: the roles differ
    # only by file, and the two processes of a team must agree on the terms.
    # The opponent's lives under their working directory because parts of the
    # config are read relative to the process's cwd, not to `--config`.
    roots = {"us": both_roles(work / "us"), "them": both_roles(theirs / "config")}
    for root in roots.values():
        terms(root, games)
    # `opens` names OUR group's role in mini-game 1; the opponent's view of
    # the same series is the mirror. Every rehearsal until 2026-08-22 ran
    # opens=thief only — the exact blind spot Naji asked about after the g4
    # failures: the counted format lets the pairing agree either opener, and
    # a path nobody has ever run is a path that fails at 20:00.
    ours, theirs_open = opens, ("police" if opens == "thief" else "thief")
    rows = []
    for name, side, cwd, role, opening, mine, door, doors, extra in (
        ("us-thief", "us", THIEF, "thief", ours, us["thief"], them["cop"], us, []),
        ("us-cop", "us", COP, "police", ours, us["cop"], them["thief"], us, []),
        ("them-cop", "them", theirs, "police", theirs_open, them["cop"], us["thief"], them,
         ["--group-id", "sparring"]),
        ("them-thief", "them", theirs, "thief", theirs_open, them["thief"], us["cop"], them,
         ["--group-id", "sparring"]),
    ):
        config = configure(roots[side], role, mine, door, doors)
        rows.append((name, cwd, config, opening, [*voice, *extra]))
    print(f"us cop {us['cop']} thief {us['thief']} · them cop {them['cop']} thief {them['thief']}")
    return rows


def run(games: int, timeout: float, quiet: bool, opens: str = "thief") -> int:
    """Play a split series between two split teams and report what happened."""
    with tempfile.TemporaryDirectory() as raw:
        work = Path(raw)
        logs: dict[str, Path] = {}
        peers: dict[str, subprocess.Popen] = {}
        rows = plan(work, games, ["--quiet"] if quiet else ["--talk"], opens=opens)
        for name, cwd, config, opening, extra in rows:
            logs[name] = work / f"{name}.log"
            peers[name] = launch(cwd, config, opening, logs[name], extra)
        print(f"launched {len(peers)} processes; {games} mini-games")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and any(p.poll() is None for p in peers.values()):
            time.sleep(2)
        failed = False
        for name, process in peers.items():
            if process.poll() is None:
                process.kill()
                print(f"{name}: TIMED OUT after {timeout:.0f}s")
                failed = True
            elif process.returncode != 0:
                print(f"{name}: exited {process.returncode}")
                failed = True
        keep = Path(os.environ.get("SPLIT_REHEARSAL_LOGS", "") or work / "keep")
        keep.mkdir(parents=True, exist_ok=True)
        for name, path in logs.items():
            shutil.copy(path, keep / f"{name}.log")
        print(f"logs kept in {keep}")
        return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--talk", action="store_true", help="LLM hints and scent, as in a match")
    parser.add_argument("--opens", choices=["thief", "police"], default="thief",
                        help="OUR group's role in mini-game 1")
    args = parser.parse_args(argv)
    return run(args.games, args.timeout, quiet=not args.talk, opens=args.opens)


if __name__ == "__main__":
    sys.exit(main())
