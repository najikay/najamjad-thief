"""The diagnostic logging channel (T-0311, T-0423, guidelines §7.2).

Two things are worth testing here and one is not. Whether a particular line
reaches a particular file is Python's problem; whether **our config is actually
applied** and whether **a broken config can stop a match** are ours.

The second matters more. Logging is the least important subsystem in the
project and the one with the most opportunities to raise at startup — a missing
directory, a bad handler class, a file the process cannot open. Losing a league
game to a logging misconfiguration would be an absurd way to lose.
"""

import json
import logging
from pathlib import Path

import pytest

from najamjad_agent.shared.logging_setup import DEFAULT_PATH, load_config, setup_logging

CONFIG = Path("config/logging_config.json")


def test_the_shipped_config_is_valid_json_with_a_version():
    """Every shipped config carries a version (guidelines §7.2)."""
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert raw["version"] == 1, "dictConfig's own schema version"
    assert raw["_config_version"] == "1.00", "our config version (guidelines §7.2)"


def test_our_annotations_are_stripped_before_python_sees_them():
    """`dictConfig` rejects keys it does not recognise, and the file is written
    to be read by a person too."""
    loaded = load_config(CONFIG)

    assert not [key for key in loaded if key.startswith("_")]
    assert "handlers" in loaded and "loggers" in loaded


def test_the_shipped_config_actually_applies(tmp_path):
    """The point of the file: it is used, not decorative."""
    assert setup_logging(CONFIG, workspace=tmp_path) is True

    logger = logging.getLogger("najamjad_agent.net")
    assert logger.handlers, "our logger must end up with the configured handlers"
    assert logger.propagate is False, "configured explicitly, so it is not inherited"


def test_a_missing_config_is_reported_and_does_not_raise(tmp_path):
    """A match must not be lost to a logging misconfiguration."""
    assert setup_logging(tmp_path / "absent.json", workspace=tmp_path) is False


def test_a_malformed_config_is_reported_and_does_not_raise(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"version": 1, "handlers": {"x": {"class": "no.such.Handler"}}}', "utf-8")

    assert setup_logging(broken, workspace=tmp_path) is False


def test_unparseable_json_is_reported_and_does_not_raise(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json at all", encoding="utf-8")

    assert setup_logging(broken, workspace=tmp_path) is False


def test_a_fresh_clone_with_no_workspace_still_configures(tmp_path):
    """`RotatingFileHandler` does not create its directory; it raises at
    configuration time, which would take the whole setup down over a folder."""
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["handlers"]["file"]["filename"] = str(tmp_path / "deep" / "nested" / "diagnostic.log")
    written = tmp_path / "config.json"
    written.write_text(json.dumps(config), encoding="utf-8")

    assert setup_logging(written, workspace=tmp_path / "workspace") is True
    assert (tmp_path / "deep" / "nested").is_dir()


def test_the_default_path_is_the_shipped_file():
    assert Path("config/logging_config.json") == DEFAULT_PATH


@pytest.mark.parametrize("logger_name", ["httpx", "uvicorn.access"])
def test_noisy_third_party_loggers_are_quietened(logger_name):
    """Their INFO output would bury ours during a match."""
    configured = load_config(CONFIG)["loggers"][logger_name]

    assert configured["level"] == "WARNING"


def test_the_diagnostic_channel_is_not_the_event_log():
    """ADR-008: the game record is the event bus. A log line is for reading, an
    event is evidence, and the audit trail must not fill up with prose."""
    filenames = [
        handler.get("filename", "")
        for handler in load_config(CONFIG)["handlers"].values()
    ]

    assert not any("events.jsonl" in name for name in filenames)
