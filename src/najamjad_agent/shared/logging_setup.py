"""Applying `config/logging_config.json` at startup (guidelines §7.2).

This is the **diagnostic** channel and nothing more: library warnings, stack
traces, and messages meant for a human watching a terminal. The *game* record is
the event bus (`workspace/events.jsonl`, ADR-008), and the two are deliberately
separate — a log line is for reading, an event is evidence, and mixing them
means either losing diagnostics in the audit trail or putting unverifiable prose
where a grader expects records.

Logging must never be able to stop a match. A missing or malformed config is
reported once, on the channel of last resort, and the agent plays on with
Python's defaults; a game lost to a logging misconfiguration would be an
absurd way to lose.
"""

from __future__ import annotations

import json
import logging
import logging.config
from pathlib import Path

DEFAULT_PATH = Path("config/logging_config.json")
#: Keys `dictConfig` would choke on — ours are documentation, not schema.
_COMMENT_PREFIX = "_"


def _strip_comments(config: dict) -> dict:
    """Drop our underscore-prefixed annotations before handing it to Python.

    `dictConfig` rejects keys it does not recognise, and the file is written to
    be read by a person as well as by the runtime.
    """
    return {key: value for key, value in config.items() if not key.startswith(_COMMENT_PREFIX)}


def load_config(path: Path | str = DEFAULT_PATH) -> dict:
    """Read the logging configuration, comments removed."""
    return _strip_comments(json.loads(Path(path).read_text(encoding="utf-8")))


def setup_logging(path: Path | str = DEFAULT_PATH, workspace: Path | str = "workspace") -> bool:
    """Configure logging from the file; report whether it was applied.

    Returns `False` rather than raising on any failure. The caller is an
    entrypoint that is about to play a match, and the correct response to a
    broken logging config is to say so and carry on.
    """
    try:
        config = load_config(path)
        _ensure_log_directories(config, Path(workspace))
        logging.config.dictConfig(config)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # `basicConfig` rather than our own logger: the configuration that would
        # have given us one is precisely what just failed.
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger(__name__).warning("logging config not applied (%s): %s", path, error)
        return False
    return True


def _ensure_log_directories(config: dict, workspace: Path) -> None:
    """Create the directories any file handler writes into.

    A fresh clone has no `workspace/`, and `RotatingFileHandler` does not create
    one — it raises at configuration time, which would take the whole logging
    setup down over a missing folder.
    """
    for handler in config.get("handlers", {}).values():
        filename = handler.get("filename")
        if filename:
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
