"""App-level settings — where files go and which subsystems run.

Separate from both other config files on purpose, and the distinction is the
point of the module:

* `game.json` is **agreed** with the opponent and signed;
* `<role>/game.toml` is **private** to this peer but still about the match;
* `setup.json` is about the **application** — paths, the local UI port, feature
  toggles — and would be the same whoever we played.

These were previously literals in `bootstrap` reached through `manager.get(...)`
with a default that nothing ever overrode, which is a hardcoded tunable wearing
a config lookup's clothes (guidelines §7.2, threshold zero).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("config/setup.json")


def load_setup(path: Path | str = DEFAULT_PATH) -> dict[str, Any]:
    """Read the app settings; an absent file is not fatal.

    A missing `setup.json` must not stop a match — the callers all pass a
    sensible default alongside the key, so the agent degrades to the behaviour
    it had before the file existed rather than refusing to start.
    """
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def setting(setup: dict[str, Any], dotted: str, default: Any) -> Any:
    """Read `"ui.port"` out of the loaded settings, or fall back.

    Underscore-prefixed keys are documentation for whoever opens the file and
    are never addressable, so a note can never shadow a setting.
    """
    node: Any = setup
    for part in dotted.split("."):
        if part.startswith("_") or not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def save_setup(setup: dict[str, Any], path: Path | str = DEFAULT_PATH) -> None:
    """Write the app settings back, preserving everything not being changed.

    Writing lives here rather than in the modules that toggle a flag, so
    `setup.json` has exactly one reader and one writer. Indented and
    `ensure_ascii=False` because a person edits this file by hand — deliberately
    *not* the canonical wire encoding, which is compact and sorted for audit
    stability and would make the config unreadable.
    """
    Path(path).write_text(
        json.dumps(setup, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


#: The hosts that keep the dashboard on the machine it runs on.
LOOPBACK = "127.0.0.1"
LOOPBACK_HOSTS = frozenset({LOOPBACK, "localhost", "::1"})


def dashboard_bind(setup: dict[str, Any], override: str = "") -> tuple[str, int]:
    """Where the dashboard listens — `ui.host` and `ui.port`, both honoured.

    `override` is the per-run `--dashboard-host` value, applied here rather than
    by the caller so `bootstrap` needs no second import for it: that file sits
    at its line budget, and isort would spend six lines on the name alone.

    `ui.host` has sat in `config/setup.json`, with a note explaining why it is
    loopback, since the file was written; nothing ever read it, so the bind was
    hard-coded in `ui/server.py` and the key was decoration. It matters on WSL2,
    where a Windows browser reaches a loopback-bound server only for as long as
    localhost forwarding holds — and when it stops there was no supported way to
    move the bind, only editing the source.

    Still defaults to loopback. The note beside the key is a rules argument
    rather than a preference: the dashboard renders our belief grid and our
    sealed state, so anything that can reach it gets what commit-reveal exists
    to hide (rules 8-9). Moving it is a decision the operator makes and the
    event log records, not something a default should make for them.
    """
    host = str(setting(setup, "ui.host", LOOPBACK) or LOOPBACK)
    return dashboard_override(override, (host, int(setting(setup, "ui.port", 8000))))


def dashboard_override(value: str, default: tuple[str, int]) -> tuple[str, int]:
    """Read `--dashboard-host` as `HOST`, `HOST:PORT`, or `:PORT`.

    A split match runs two processes and both panels defaulted to 8000, so the
    second bound nothing while its terminal still implied a dashboard — the
    operator read the *first* process's board for the whole series. Giving the
    second its own port is the fix, and it rides on the existing flag rather
    than a new one because `cli.py` stands at the 150-line cap and the course
    rule is to split files, never to compress them (guidelines §3.2).

    Only a *single* colon separates a port, so bare IPv6 literals such as `::1`
    pass through as hosts. A non-numeric port raises here, at startup, which is
    the right moment: quietly ignoring the typo is the defect this whole change
    exists to remove.
    """
    host, port = default
    text = value.strip()
    if not text:
        return host, port
    if text.count(":") == 1:
        left, _, right = text.partition(":")
        return (left or host), (int(right) if right else port)
    return text, port
