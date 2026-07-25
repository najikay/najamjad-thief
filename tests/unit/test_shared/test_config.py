"""Tests for configuration loading: overlay order, versions, referenced files."""

import json
from pathlib import Path

import pytest

from najamjad_agent.shared.config import ConfigError, ConfigManager

TOML = """
version = "1.00"

[game]
group_name = "NajAmjad"

[network]
my_port = 8802
opponent_url = "http://127.0.0.1:8801/mcp"

[tunnel]
provider = "cloudflare"
hostname = "cop.najamjad.dev"

[movement_and_barriers]
max_barriers = 14
"""


def _role_dir(tmp_path: Path, toml: str = TOML) -> Path:
    role = tmp_path / "police"
    role.mkdir()
    (role / "game.toml").write_text(toml, encoding="utf-8")
    return role


def test_private_config_loads(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    assert config.get("game.group_name") == "NajAmjad"
    assert config.get("network.my_port") == 8802


def test_a_missing_private_config_is_a_boot_failure(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing private config"):
        ConfigManager.load(tmp_path / "nowhere")


def test_the_signed_contract_overrides_private_values(tmp_path: Path) -> None:
    """A private file must never be able to weaken an agreed term (PAGE 127)."""
    role = _role_dir(tmp_path)
    contract = tmp_path / "game.json"
    contract.write_text(json.dumps({"movement_and_barriers": {"max_barriers": 20}}), encoding="utf-8")
    config = ConfigManager.load(role, shared_config=contract)
    assert config.get("movement_and_barriers.max_barriers") == 20


def test_private_only_keys_survive_the_overlay(tmp_path: Path) -> None:
    role = _role_dir(tmp_path)
    contract = tmp_path / "game.json"
    contract.write_text(json.dumps({"movement_and_barriers": {"max_moves": 40}}), encoding="utf-8")
    config = ConfigManager.load(role, shared_config=contract)
    assert config.get("network.my_port") == 8802, "private settings are untouched"
    assert config.get("movement_and_barriers.max_barriers") == 14
    assert config.get("movement_and_barriers.max_moves") == 40


def test_a_required_contract_that_is_absent_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="signed contract not found"):
        ConfigManager.load(_role_dir(tmp_path), shared_config=tmp_path / "none.json", require_shared=True)


def test_an_unsupported_version_refuses_to_boot(tmp_path: Path) -> None:
    """Better a loud boot failure than silent drift mid-match."""
    role = _role_dir(tmp_path, TOML.replace('version = "1.00"', 'version = "9.99"'))
    with pytest.raises(ConfigError, match="not supported"):
        ConfigManager.load(role)


def test_a_missing_version_refuses_to_boot(tmp_path: Path) -> None:
    role = _role_dir(tmp_path, TOML.replace('version = "1.00"', ""))
    with pytest.raises(ConfigError, match="not supported"):
        ConfigManager.load(role)


def test_a_referenced_file_that_does_not_exist_fails_at_load(tmp_path: Path) -> None:
    """A6 lesson: the prompts directory was missing and nobody found out."""
    toml = TOML + '\n[strategy]\nprompt_file = "does/not/exist.txt"\n'
    with pytest.raises(ConfigError, match="points at a missing file"):
        ConfigManager.load(_role_dir(tmp_path, toml))


def test_a_referenced_file_that_exists_passes(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("hi", encoding="utf-8")
    toml = TOML + f'\n[strategy]\nprompt_file = "{prompt.as_posix()}"\n'
    assert ConfigManager.load(_role_dir(tmp_path, toml)).get("strategy.prompt_file")


def test_dotted_lookup_returns_the_default_when_absent(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    assert config.get("nothing.here", "fallback") == "fallback"
    assert config.get("network.nothing") is None


def test_require_raises_a_clear_error_for_a_missing_key(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    with pytest.raises(ConfigError, match="required configuration 'llm.model'"):
        config.require("llm.model")


def test_require_returns_a_present_value(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    assert config.require("tunnel.hostname") == "cop.najamjad.dev"


def test_section_returns_a_whole_table(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    assert config.section("tunnel") == {"provider": "cloudflare", "hostname": "cop.najamjad.dev"}
    assert config.section("absent") == {}


def test_as_dict_is_a_detached_copy(tmp_path: Path) -> None:
    config = ConfigManager.load(_role_dir(tmp_path))
    snapshot = config.as_dict()
    snapshot["network"]["my_port"] = 9999
    assert config.get("network.my_port") == 8802


def test_sources_record_where_values_came_from(tmp_path: Path) -> None:
    role = _role_dir(tmp_path)
    contract = tmp_path / "game.json"
    contract.write_text("{}", encoding="utf-8")
    config = ConfigManager.load(role, shared_config=contract)
    assert config.sources["toml"].name == "game.toml"
    assert config.sources["json"].name == "game.json"
