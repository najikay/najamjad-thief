"""The config version-bump procedure (T-0323).

`SUPPORTED_CONFIG_VERSIONS` is the single place a new config schema is admitted,
and the order of operations matters: **widen the supported set first, ship the
config second**. Doing it the other way round means the agent refuses to boot on
its own configuration — which is the correct behaviour and a terrible surprise
five minutes before a match.

These tests exist because that refusal is easy to mistake for a bug and
"fix" by loosening the check. The check is the point: a config the code does not
understand is a config that will be *partly* understood, and partly understood
settings are how an agent plays a game under terms it never agreed to.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.shared.config import ConfigError, ConfigManager
from najamjad_agent.shared.version import CODE_VERSION, SUPPORTED_CONFIG_VERSIONS


def write_config(root: Path, version: str) -> Path:
    """A minimal but complete private config at `version`."""
    role = root / "police"
    role.mkdir(parents=True, exist_ok=True)
    (role / "game.toml").write_text(
        f'version = "{version}"\n[network]\nmy_port = 8802\n', encoding="utf-8"
    )
    (root / "game.json").write_text(json.dumps({"schema_version": "1.3"}), encoding="utf-8")
    return role


def test_the_shipped_version_is_supported():
    """The most basic consistency: we can boot on what we ship."""
    assert CODE_VERSION in SUPPORTED_CONFIG_VERSIONS


def test_a_supported_version_loads(tmp_path):
    role = write_config(tmp_path, CODE_VERSION)

    manager = ConfigManager.load(role, shared_config=tmp_path / "game.json")

    assert manager.get("version") == CODE_VERSION


def test_an_unsupported_version_refuses_to_boot(tmp_path):
    """The whole point of the procedure.

    A loud failure at startup beats a silent drift mid-match, where a setting
    the code half-understands decides a game.
    """
    role = write_config(tmp_path, "9.99")

    with pytest.raises(ConfigError, match="not supported"):
        ConfigManager.load(role, shared_config=tmp_path / "game.json")


def test_the_refusal_names_both_the_offending_version_and_the_accepted_ones(tmp_path):
    """An operator under time pressure needs the fix in the message."""
    role = write_config(tmp_path, "2.00")

    with pytest.raises(ConfigError) as failure:
        ConfigManager.load(role, shared_config=tmp_path / "game.json")

    message = str(failure.value)
    assert "2.00" in message
    assert CODE_VERSION in message


def test_widening_the_supported_set_is_what_admits_a_new_version(tmp_path, monkeypatch):
    """Step one of the procedure, in isolation.

    Ship the config first and the agent refuses its own settings; widen first
    and the same file loads. That asymmetry is the procedure.
    """
    role = write_config(tmp_path, "1.01")

    with pytest.raises(ConfigError):
        ConfigManager.load(role, shared_config=tmp_path / "game.json")

    monkeypatch.setattr(
        "najamjad_agent.shared.config.SUPPORTED_CONFIG_VERSIONS", ("1.00", "1.01")
    )

    assert ConfigManager.load(role, shared_config=tmp_path / "game.json").get("version") == "1.01"


def test_a_missing_version_is_refused_like_a_wrong_one(tmp_path):
    """Absent is not 'probably current'."""
    role = tmp_path / "police"
    role.mkdir(parents=True)
    (role / "game.toml").write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    (tmp_path / "game.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigError, match="not supported"):
        ConfigManager.load(role, shared_config=tmp_path / "game.json")


def test_every_shipped_json_config_declares_a_version():
    """The procedure only works if there is a version to bump."""
    for name in ("config/setup.json", "config/rate_limits.json", "config/logging_config.json"):
        raw = json.loads(Path(name).read_text(encoding="utf-8"))
        declared = raw.get("version") or raw.get("_config_version") or (
            raw.get("rate_limits", {}) or {}
        ).get("version")
        assert declared, f"{name} declares no version"
