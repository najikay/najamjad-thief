"""Play a full series between the two repos, as two real processes (T-2101).

    uv run python scripts/two_process_match.py

Everything the in-memory tests fake is real here: two OS processes, two MCP
servers, HTTP between them. That is the closest thing to a league match we can
run without an opponent, and it is the only setup that would have caught the
argument-name mismatch — which every in-process test happily passed.

Each peer gets a temporary config with the other's URL, so nothing in the
committed configs is touched.
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
SIBLING = ROOT.parent / ("najamjad-thief" if ROOT.name == "najamjad-cop" else "najamjad-cop")
READY = "agent online at"


def free_port() -> int:
    """A port the OS says is free right now.

    Hard-coded ports made the harness fail with "already in use" whenever a
    previous run left a peer behind — reporting a stale process as a broken
    match. Asking the OS is both correct and self-cleaning.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def prepare(repo: Path, role: str, my_port: int, their_port: int, workspace: Path) -> Path:
    """Copy the repo's config into a temp dir, pointed at the other peer."""
    source = repo / "config"
    target = workspace / f"{role}-config"
    shutil.copytree(source, target)
    toml = target / role / "game.toml"
    text = toml.read_text(encoding="utf-8")
    text = _set(text, "my_port", str(my_port))
    text = _set(text, "opponent_url", f'"http://127.0.0.1:{their_port}/mcp"')
    toml.write_text(text, encoding="utf-8")
    shared = json.loads((target / "game.json").read_text(encoding="utf-8"))
    shared["network_and_league"]["num_games"] = 2  # a short series keeps the run quick
    (target / "game.json").write_text(json.dumps(shared, indent=2), encoding="utf-8")
    return target / role


def _set(text: str, key: str, value: str) -> str:
    """Replace `key = ...` on its own line, preserving everything else."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            lines.append(f"{key} = {value}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def launch(repo: Path, config: Path, log: Path) -> subprocess.Popen:
    """Start one peer's `match` verb as its own process.

    Unbuffered: redirected stdout is block-buffered by default, so a peer we
    have to kill takes its entire account of what happened with it — the first
    runs looked like silent hangs purely because nothing had been flushed.
    """
    handle = log.open("w", encoding="utf-8")
    environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        ["uv", "run", "python", "-u", "-m", "najamjad_agent.cli", "match",
         "--config", str(config), "--no-tunnel", "--no-dashboard"],
        cwd=repo, stdout=handle, stderr=subprocess.STDOUT, text=True, env=environment,
    )


def wait_for(log: Path, marker: str, timeout: float) -> bool:
    """Poll a log until `marker` appears or the deadline passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists() and marker in log.read_text(encoding="utf-8", errors="replace"):
            return True
        time.sleep(0.5)
    return False


def run(timeout: float) -> int:
    """Run both peers to completion and report what happened."""
    if not SIBLING.exists():
        print(f"sibling repo not found at {SIBLING}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        cop_port, thief_port = free_port(), free_port()
        cop_config = prepare(
            ROOT if ROOT.name == "najamjad-cop" else SIBLING, "police", cop_port, thief_port, workspace
        )
        thief_config = prepare(
            SIBLING if ROOT.name == "najamjad-cop" else ROOT, "thief", thief_port, cop_port, workspace
        )
        print(f"police on {cop_port}, thief on {thief_port}")
        cop_repo = ROOT if ROOT.name == "najamjad-cop" else SIBLING
        thief_repo = SIBLING if ROOT.name == "najamjad-cop" else ROOT
        logs = {"police": workspace / "police.log", "thief": workspace / "thief.log"}

        peers = {
            "police": launch(cop_repo, cop_config, logs["police"]),
            "thief": launch(thief_repo, thief_config, logs["thief"]),
        }
        print("launched both peers; waiting for the series to finish…")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and any(p.poll() is None for p in peers.values()):
            time.sleep(1)

        failed = False
        for role, process in peers.items():
            if process.poll() is None:
                process.kill()
                print(f"{role}: TIMED OUT after {timeout:.0f}s")
                failed = True
            elif process.returncode != 0:
                print(f"{role}: exited {process.returncode}")
                failed = True
            print(f"--- {role} ---")
            print(logs[role].read_text(encoding="utf-8", errors="replace").strip()[-1200:])
        return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=180.0)
    return run(parser.parse_args(argv).timeout)


if __name__ == "__main__":
    sys.exit(main())
