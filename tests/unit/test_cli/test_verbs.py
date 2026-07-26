"""The CLI verbs: exit codes, output, and one SDK call each.

Exit codes are the contract, because these commands run in scripts and CI:
0 worked, 1 ran with a bad answer (not ready, tampered), 2 could not run. A
verb that collapsed "tampered" into "broken file" would make an audit
indistinguishable from a typo.
"""

from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from najamjad_agent.cli import app

GOLDENS = Path(__file__).resolve().parents[2] / "goldens" / "artifacts"
REFERENCE = GOLDENS / "log_segal-police-team-vs-segal-thief-team_g01.json"
TAMPERED = GOLDENS / "log_tampered_step7.json"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_the_help_lists_every_verb(runner):
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for verb in ("peer", "preflight", "replay", "archive", "version"):
        assert verb in result.stdout


def test_version_prints_the_code_version(runner):
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "1.00"


def test_replay_verifies_a_clean_log_and_exits_zero(runner):
    result = runner.invoke(app, ["replay", str(REFERENCE)])

    assert result.exit_code == 0
    assert "Verified OK" in result.stdout


def test_replay_exits_one_on_a_tampered_log(runner):
    """Distinct from exit 2 — the file was fine, the game was not."""
    result = runner.invoke(app, ["replay", str(TAMPERED)])

    assert result.exit_code == 1
    assert "TAMPERED" in result.stdout


def test_replay_exits_two_on_a_missing_log(runner, tmp_path):
    result = runner.invoke(app, ["replay", str(tmp_path / "absent.json")])

    assert result.exit_code == 2
    assert "no such log" in result.output


def test_preflight_prints_the_checklist_and_uses_the_report_exit_code(runner):
    report = mock.Mock(exit_code=1, render=mock.Mock(return_value="[FAIL] opponent_url: unset"))
    sdk = mock.Mock()
    sdk.actions.preflight.return_value = report

    with mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk):
        result = runner.invoke(app, ["preflight"])

    assert result.exit_code == 1
    assert "[FAIL] opponent_url" in result.stdout


def test_a_ready_preflight_exits_zero(runner):
    report = mock.Mock(exit_code=0, render=mock.Mock(return_value="preflight: READY"))
    sdk = mock.Mock()
    sdk.actions.preflight.return_value = report

    with mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk):
        result = runner.invoke(app, ["preflight"])

    assert result.exit_code == 0


def test_archive_reports_what_it_bundled(runner, tmp_path):
    report = mock.Mock(file_count=7, excluded_secrets=[], missing_sources=[])
    sdk = mock.Mock()
    sdk.actions.archive_match.return_value = report

    with mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk):
        result = runner.invoke(app, ["archive", str(tmp_path / "m.zip")])

    assert result.exit_code == 0
    assert "archived 7 file(s)" in result.stdout


def test_archive_names_withheld_secrets_and_empty_sources(runner, tmp_path):
    """An empty archive with no explanation reads as a bug."""
    report = mock.Mock(
        file_count=0, excluded_secrets=["secrets/token.json"], missing_sources=["artifacts"]
    )
    sdk = mock.Mock()
    sdk.actions.archive_match.return_value = report

    with mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk):
        result = runner.invoke(app, ["archive", str(tmp_path / "m.zip")])

    assert "withheld secret: secrets/token.json" in result.output
    assert "nothing found for: artifacts" in result.output


def test_peer_starts_the_agent_and_reports_its_public_url(runner):
    sdk = mock.Mock()
    sdk.actions.start_peer.return_value = "https://cop.4laboratory.com/mcp"

    with (
        mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk),
        mock.patch("najamjad_agent.cli._serve_until_interrupted") as serve,
    ):
        result = runner.invoke(app, ["peer"])

    assert result.exit_code == 0
    assert "https://cop.4laboratory.com/mcp" in result.stdout
    assert serve.called


def test_peer_honours_no_tunnel_and_no_dashboard(runner):
    sdk = mock.Mock()

    with (
        mock.patch("najamjad_agent.cli.build_sdk", return_value=sdk),
        mock.patch("najamjad_agent.cli._serve_until_interrupted"),
    ):
        runner.invoke(app, ["peer", "--no-tunnel", "--no-dashboard"])

    sdk.actions.start_peer.assert_called_once_with(with_tunnel=False, with_dashboard=False)


def test_an_interrupted_peer_stops_the_tunnel_before_exiting():
    """An unstopped tunnel points a public hostname at a dead port."""
    from najamjad_agent.cli import _serve_until_interrupted

    sdk = mock.Mock()
    with mock.patch("signal.sigwait", return_value=2):
        _serve_until_interrupted(sdk)

    sdk.actions.stop_peer.assert_called_once()
