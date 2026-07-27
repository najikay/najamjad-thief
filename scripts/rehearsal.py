"""Match-day rehearsal against the course reference simulator (T-2307).

    uv run python scripts/rehearsal.py --games 2

Our agent against an implementation **we did not write**, as two real OS
processes over real MCP/HTTP. This is the closest thing to a league match
available before an opponent exists, and it is the only setup that has ever
caught our interop defects — the argument-name mismatch, the audit envelope, and
the step guard that ended a series after game 1 all passed every test we wrote
against ourselves.

The simulator is expected at `../reference-sim`. Both peers get a temporary
config so nothing committed is touched, and both are given the **same**
`num_games`: a terms mismatch is a legitimate refusal to play, not a rehearsal.
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

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT.parent / "najamjad-thief"
REFERENCE = ROOT.parent / "reference-sim"


def free_port() -> int:
    """A port the OS says is free right now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _set_toml(path: Path, key: str, value: str) -> None:
    """Replace `key = ...` on its own line."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        lines.append(f"{key} = {value}" if stripped.startswith((f"{key} ", f"{key}=")) else line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_games(path: Path, games: int) -> None:
    """Agree the series length in a shared game.json."""
    terms = json.loads(path.read_text(encoding="utf-8"))
    terms.setdefault("network_and_league", {})["num_games"] = games
    path.write_text(json.dumps(terms, indent=2), encoding="utf-8")


def prepare_ours(workspace: Path, my_port: int, their_port: int, games: int) -> Path:
    """Our thief's config, pointed at the simulator."""
    target = workspace / "ours"
    shutil.copytree(OURS / "config", target)
    _set_toml(target / "thief/game.toml", "my_port", str(my_port))
    _set_toml(target / "thief/game.toml", "opponent_url", f'"http://127.0.0.1:{their_port}/mcp"')
    _set_games(target / "game.json", games)
    return target / "thief"


def prepare_reference(workspace: Path, my_port: int, their_port: int, games: int) -> Path:
    """The simulator's police config, pointed at us."""
    target = workspace / "reference"
    shutil.copytree(REFERENCE / "config", target)
    _set_toml(target / "police/game.toml", "my_port", str(my_port))
    _set_toml(target / "police/game.toml", "opponent_url", f'"http://127.0.0.1:{their_port}/mcp"')
    _set_games(target / "police/game.json", games)
    return target / "police"


def launch(command: list[str], cwd: Path, log: Path) -> subprocess.Popen:
    """Start one peer unbuffered, so a kill still leaves its account behind."""
    handle = log.open("w", encoding="utf-8")
    environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
    # The parent's VIRTUAL_ENV points at *our* venv and confuses uv in the
    # sibling project, which then warns on every line of output.
    environment.pop("VIRTUAL_ENV", None)
    return subprocess.Popen(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                            text=True, env=environment)


def wait_until_listening(port: int, timeout: float) -> bool:
    """Poll until something accepts TCP on `port`.

    The reference dials its opponent **once, at startup, with no retry**: if we
    are not already listening it prints `Opponent MCP server unreachable` and
    exits. Our cold start is ~15 s (importing the MCP stack), so launching both
    at once fails every time and tells you nothing about interop.

    This is a real match-day constraint, not just a harness detail — whoever
    starts second must wait for the other to be up. It is in the runbook and in
    `docs/HOW_TO_PLAY_US.md` for that reason.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def run(games: int, timeout: float) -> int:
    """Play a rehearsal series and report what happened."""
    for name, path in (("our thief", OURS), ("reference simulator", REFERENCE)):
        if not path.exists():
            print(f"{name} not found at {path}", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        ours_port, reference_port = free_port(), free_port()
        ours = prepare_ours(workspace, ours_port, reference_port, games)
        reference = prepare_reference(workspace, reference_port, ours_port, games)
        logs = {"ours": workspace / "ours.log", "reference": workspace / "reference.log"}
        print(f"our thief on {ours_port}, reference police on {reference_port}, {games} game(s)")

        # We start first and wait to be listening, because the reference does
        # not retry its opening connection.
        peers = {"ours": launch(
            ["uv", "run", "najamjad-thief", "match", "--config", str(ours),
             "--no-tunnel", "--no-dashboard"], OURS, logs["ours"])}
        if not wait_until_listening(ours_port, timeout=90):
            peers["ours"].kill()
            print(f"our peer never listened on {ours_port}; log follows")
            print(logs["ours"].read_text(encoding="utf-8", errors="replace")[-1500:])
            return 1
        print("our thief is listening; starting the reference")
        peers["reference"] = launch(
            ["uv", "run", "python", "-c",
             "from police_thief.cli import main; raise SystemExit(main())",
             "peer", "--role", "police", "--no-gui", "--stub-llm",
             "--config", str(reference)], REFERENCE, logs["reference"])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and any(p.poll() is None for p in peers.values()):
            time.sleep(1)

        failed = False
        for name, process in peers.items():
            if process.poll() is None:
                process.kill()
                print(f"{name}: TIMED OUT after {timeout:.0f}s")
                failed = True
            elif process.returncode != 0:
                print(f"{name}: exited {process.returncode}")
                failed = True
            print(f"--- {name} ---")
            print(logs[name].read_text(encoding="utf-8", errors="replace").strip()[-1500:])
        return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    return run(args.games, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
