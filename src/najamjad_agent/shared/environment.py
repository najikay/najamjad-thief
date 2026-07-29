"""Loading `.env`, so a key written there is a key the agent can actually use.

This existed as a gap rather than a bug: `.env-example` told the operator to
copy the file and fill in real values, `.gitignore` protected it, the README
referred to it — and nothing in the codebase ever read it. A key pasted into
`.env` had exactly the same effect as no key at all, and the failure was
silent, because a vendor without credentials is skipped rather than reported
as broken.

`python-dotenv` was already present in the lock file as a *transitive*
dependency of the MCP stack, which is not the same as being ours to call: a
parent package dropping it would have broken us at import time for reasons
nobody would connect to this. It is now declared in `pyproject.toml`.

**The environment wins over the file.** `override=False` is the whole contract:
a variable exported in the shell — or injected by CI, or set for one command —
is a deliberate act by whoever ran the process, and a checked-out file must not
quietly replace it. That ordering is also what keeps CI honest, since CI sets
secrets as environment variables and ships no `.env` at all.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_ENV = Path(".env")


def load_env(path: Path | str = DEFAULT_ENV) -> bool:
    """Read `.env` into the environment. Returns whether a file was found.

    Input: path to an env file; the default is `.env` beside the project root.
    Output: True if the file existed and was read, False otherwise.
    Setup: none. A missing file is the normal case in CI and on a fresh clone,
        so it is not an error and never raises — the agent simply runs with
        whatever the environment already holds.
    """
    target = Path(path)
    if not target.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - declared dependency, defensive only
        return False
    # override=False: an exported variable beats a file on disk.
    load_dotenv(target, override=False)
    return True
