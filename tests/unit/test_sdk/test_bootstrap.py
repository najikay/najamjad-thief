"""The composition root, and the contract an outside consumer actually gets.

The role comes from the config directory, not a guess: the two repos share a
byte-identical core, so the files on disk are the only honest answer to "which
side am I?".
"""

from pathlib import Path

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.sdk.bootstrap import build_sdk, default_config_path, resolve_role

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture()
def workspace(tmp_path) -> Path:
    return tmp_path / "ws"


def test_the_role_comes_from_the_config_directory(tmp_path):
    assert resolve_role(tmp_path / "police") is Role.COP
    assert resolve_role(tmp_path / "thief") is Role.THIEF


def test_an_explicit_role_overrides_the_directory(tmp_path):
    assert resolve_role(tmp_path / "police", override="thief") is Role.THIEF


def test_an_unknown_role_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        resolve_role(tmp_path / "police", override="referee")


def test_this_repo_ships_exactly_one_role_config():
    """Book rules 1-2: the cop and thief configs are kept strictly apart."""
    present = [role for role in Role if (REPO / "config" / role.value / "game.toml").exists()]

    assert len(present) == 1
    assert default_config_path().name == present[0].value


def test_building_from_the_real_config_produces_a_wired_sdk(workspace):
    """Before serving, the advertised URL is local — not the tunnel hostname.

    This used to assert `https://`, which encoded a defect: a configured tunnel
    is not a running one, and printing the permanent hostname while nothing
    listens on it hands an opponent a URL that makes us look absent.
    """
    sdk = build_sdk(workspace=workspace, dashboard=False)

    assert sdk.actions.serving is False
    assert not sdk.actions.public_url.startswith("https://"), "nothing is listening yet"


def test_the_preflight_reads_the_real_configuration(workspace):
    """Every check must prove something — see test_preflight_checks for why."""
    report = build_sdk(workspace=workspace, dashboard=False).actions.preflight()

    names = {result.name for result in report.results}
    assert {"config", "port", "opponent_url", "email_recipient"} <= names


def test_a_dashboard_is_attached_when_requested(workspace):
    sdk = build_sdk(workspace=workspace, dashboard=True)

    assert sdk.actions._dashboard is not None


def test_no_dashboard_is_attached_when_disabled(workspace):
    sdk = build_sdk(workspace=workspace, dashboard=False)

    assert sdk.actions.start_dashboard() == ""


def test_a_missing_config_directory_fails_with_a_clear_message(tmp_path):
    from najamjad_agent.shared.config import ConfigError

    with pytest.raises(ConfigError, match="missing private config"):
        build_sdk(config=tmp_path / "nowhere", dashboard=False)


def test_an_outside_consumer_can_work_through_the_sdk_alone(workspace, tmp_path):
    """T-2004: a full operation using only the public surface.

    Nothing here reaches into `domain`, `net` or `reporting` — if this test
    ever needs an internal import to do something ordinary, the facade has a
    hole in it.
    """
    from najamjad_agent.sdk import AgentSdk

    sdk = build_sdk(workspace=workspace, dashboard=False)
    assert isinstance(sdk, AgentSdk)

    report = sdk.actions.preflight()
    archive = sdk.actions.archive_match(tmp_path / "match.zip")
    verdict = sdk.actions.verify_log(
        REPO / "tests" / "goldens" / "artifacts"
        / "log_segal-police-team-vs-segal-thief-team_g01.json"
    )
    snapshot = sdk.snapshot()

    assert report.exit_code in (0, 1)
    assert archive.path.exists()
    assert verdict.banner == "Verified OK"
    assert set(snapshot) >= {"board", "turn", "budget", "report"}


def test_local_play_without_a_configured_tunnel_is_allowed(tmp_path, monkeypatch):
    """A hostname-less config means local play, not a broken agent."""
    from najamjad_agent.sdk import bootstrap

    real_load = bootstrap.ConfigManager.load

    def no_tunnel(role_dir, shared_config=None, require_shared=False):
        manager = real_load(role_dir, shared_config, require_shared)
        manager._values["tunnel"] = {}
        return manager

    monkeypatch.setattr(bootstrap.ConfigManager, "load", staticmethod(no_tunnel))
    sdk = build_sdk(workspace=tmp_path, dashboard=False)

    assert sdk.actions.public_url.startswith("http://"), "falls back to the local MCP url"


def test_the_config_root_is_returned_when_no_role_directory_exists(monkeypatch, tmp_path):
    """A clone missing its config must not silently pick the wrong side."""
    from najamjad_agent.sdk import bootstrap

    monkeypatch.setattr(bootstrap, "CONFIG_ROOT", tmp_path / "config")

    assert bootstrap.default_config_path() == tmp_path / "config"
