"""The standard match-day checklist.

The probe contract is easy to satisfy without proving anything: return `None`
and you are "not applicable", return any string and you pass. The first version
of this checklist did both by accident and reported READY with no opponent URL
set. These tests exist so a check that stops checking fails loudly.
"""

import pytest

from najamjad_agent.net.preflight import run_preflight
from najamjad_agent.net.preflight_checks import (
    config_check,
    port_check,
    required_setting,
    standard_checks,
    tunnel_check,
)
from najamjad_agent.shared.config import ConfigManager


def manager(**overrides) -> ConfigManager:
    """A config manager over an in-memory document."""
    values = {
        "version": "1.00",
        "game": {"group_id": "najamjad"},
        "network": {"opponent_url": "https://peer.example.com/mcp", "my_port": 8802},
        "email": {"recipient": "grader@example.com"},
    }
    values.update(overrides)
    return ConfigManager(values)


class FakeServer:
    host = "127.0.0.1"
    port = 8802

    def __init__(self, free: bool = True) -> None:
        self.free = free

    def preflight(self) -> None:
        if not self.free:
            raise OSError("port 8802 on 127.0.0.1 is already in use")


def test_a_present_setting_passes_and_reports_its_value():
    assert required_setting(manager(), "game.group_id")() == "najamjad"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_an_empty_setting_fails_rather_than_passing_blank(value):
    """The bug this test exists for: a blank opponent_url reported READY."""
    config = manager(network={"opponent_url": value, "my_port": 8802})

    with pytest.raises(ValueError, match="is not set"):
        required_setting(config, "network.opponent_url")()


def test_a_missing_setting_fails():
    with pytest.raises(ValueError, match="is not set"):
        required_setting(manager(), "network.nothing_here")()


def test_the_config_check_reports_the_version_it_validated():
    assert "1.00" in config_check(manager())()


def test_the_port_check_confirms_the_port_is_free():
    assert port_check(FakeServer())() == "127.0.0.1:8802 free"


def test_a_taken_port_fails_the_check():
    with pytest.raises(OSError, match="already in use"):
        port_check(FakeServer(free=False))()


def test_the_tunnel_check_reports_the_public_url():
    tunnel = type("T", (), {"public_url": "https://cop.4laboratory.com/mcp"})()

    assert tunnel_check(tunnel)() == "https://cop.4laboratory.com/mcp"


def test_no_tunnel_is_not_applicable_rather_than_a_failure():
    """Local play is a legitimate setup, not a red line."""
    assert tunnel_check(None)() is None


class StubCredentials:
    """Stands in for a loaded Gmail token.

    Injected rather than read from disk: the real loader looks at `secrets/`,
    which exists on a developer laptop and never in CI. A checklist test whose
    verdict depends on what happens to be lying around the filesystem proves
    nothing about the checklist.
    """

    valid = True


def stub_credentials() -> StubCredentials:
    return StubCredentials()


def test_a_fully_configured_agent_is_ready():
    report = run_preflight(
        standard_checks(manager(), FakeServer(), tunnel=None, credentials=stub_credentials)
    )

    assert report.ready is True
    assert report.exit_code == 0


def test_a_missing_opponent_url_blocks_readiness():
    config = manager(network={"opponent_url": "", "my_port": 8802})

    report = run_preflight(standard_checks(config, FakeServer(), credentials=stub_credentials))

    assert report.ready is False
    assert [failure.name for failure in report.failures] == ["opponent_url"]


def test_every_check_actually_proves_something():
    """A probe returning None is recorded as "not applicable" — only the
    tunnel check may legitimately do that, and only when there is no tunnel."""
    checks = standard_checks(
        manager(), FakeServer(), tunnel=None, credentials=stub_credentials
    )
    results = {name: probe() for name, probe in checks.items()}

    always_proving = {name: value for name, value in results.items() if name != "tunnel"}
    assert all(value for value in always_proving.values()), always_proving


def test_the_checklist_covers_the_settings_a_match_cannot_start_without():
    names = set(standard_checks(manager(), FakeServer()))

    assert {"opponent_url", "email_recipient", "group_id", "port", "config"} <= names


def test_unusable_gmail_credentials_block_the_match():
    """The check has to bite, or it is decoration.

    An unsent report scores like not having played (book rules 33-35), and for
    the life of this project nothing verified the mailbox was reachable — every
    match filed its artifacts and failed to send. This is the check that would
    have caught it, so it must fail rather than warn.
    """

    def unusable():
        raise RuntimeError("no Gmail token")

    report = run_preflight(
        standard_checks(manager(), FakeServer(), tunnel=None, credentials=unusable)
    )

    assert report.ready is False
    assert "gmail_credentials" in [failure.name for failure in report.failures]
