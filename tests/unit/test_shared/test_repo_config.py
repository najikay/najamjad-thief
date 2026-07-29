"""Tests for the configuration this repository actually ships.

The unit tests elsewhere use synthetic configs. These load the real files, so a
typo in the shipped `game.toml` fails in CI rather than on match day.
"""

import re
from pathlib import Path

import pytest

from najamjad_agent.net.tunnel import from_config
from najamjad_agent.shared.config import ConfigManager

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "config"
ROLE_DIR = next((path for path in (CONFIG / "police", CONFIG / "thief") if path.exists()), None)


@pytest.fixture()
def config() -> ConfigManager:
    assert ROLE_DIR is not None, "this repo must ship a role config directory"
    return ConfigManager.load(ROLE_DIR)


def test_the_shipped_config_loads_and_validates(config: ConfigManager) -> None:
    assert config.get("game.group_name") == "NajAmjad"
    assert config.get("game.group_id") == "najamjad"


def test_both_repository_links_are_declared(config: ConfigManager) -> None:
    """Book rule 49: the JSON report carries four repo links."""
    assert config.get("game.repos.cop", "").startswith("https://github.com/")
    assert config.get("game.repos.thief", "").startswith("https://github.com/")


def test_the_public_hostname_is_permanent_and_role_specific(config: ConfigManager) -> None:
    """A hostname on our own domain cannot churn the way quick tunnels do."""
    hostname = config.require("tunnel.hostname")
    assert hostname.endswith(".4laboratory.com")
    assert hostname.split(".")[0] in {"cop", "thief"}


def test_the_tunnel_builds_from_the_shipped_config(config: ConfigManager) -> None:
    tunnel = from_config(config, port=int(config.require("network.my_port")))
    assert tunnel.provider == "cloudflare"
    assert tunnel.public_url.startswith("https://")
    assert tunnel.public_url.endswith("/mcp")
    assert tunnel.name.startswith("najamjad-")


def test_cop_and_thief_use_different_ports(config: ConfigManager) -> None:
    """Both agents may run on one machine; a port clash blocks a match."""
    port = int(config.require("network.my_port"))
    assert port in {8801, 8802}


def test_role_directory_matches_the_hostname(config: ConfigManager) -> None:
    """Guards against copying the cop config into the thief repo."""
    assert ROLE_DIR is not None
    expected = "cop" if ROLE_DIR.name == "police" else "thief"
    assert config.require("tunnel.hostname").startswith(f"{expected}.")
    assert config.require("tunnel.name") == f"najamjad-{expected}"


def test_the_report_address_is_the_book_mandated_one(config: ConfigManager) -> None:
    """Appendix F Table 20: reports go ONLY to the +uoh26finalgame address."""
    assert config.require("email.recipient") == "rmisegal+uoh26finalgame@gmail.com"


def test_timeouts_respect_appendix_f(config: ConfigManager) -> None:
    assert int(config.require("network.response_timeout_seconds")) >= 30
    assert int(config.require("network.watchdog_threshold_seconds")) >= 60


def test_the_series_budget_matches_the_agreed_term(config: ConfigManager) -> None:
    assert int(config.require("llm.series_token_budget")) == 200_000


def test_no_secret_is_stored_in_the_config(config: ConfigManager) -> None:
    """Keys belong in .env; a config file is committed and would leak them."""
    flat = str(config.as_dict()).lower()
    for marker in ("sk-ant", "api_key", "password", "authtoken"):
        assert marker not in flat, f"{marker!r} appears in a committed config file"
    # A bare "sk-" matched mid-word and fired on an opponent URL — the tunnel
    # hostname `mask-matching-stevens-omissions` contains it. Real vendor keys
    # begin a value, so requiring no alphanumeric before the prefix keeps the
    # check exact without weakening it: `sk-ant-...` and `sk-proj-...` still
    # match, `ma|sk-|matching` no longer does.
    assert not re.search(r"(?<![a-z0-9])sk-[a-z0-9_-]{12,}", flat), (
        "a vendor API key appears in a committed config file"
    )
