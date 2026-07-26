"""The `--check` verb: a verdict you can put in a CI pipeline.

The exit code is the answer, so a tampered log fails a script that never reads
the output. That is the difference between a tool and a report.
"""

from pathlib import Path

import pytest

from najamjad_agent.replay.__main__ import build_parser, main

GOLDENS = Path(__file__).resolve().parents[2] / "goldens" / "artifacts"
REFERENCE = GOLDENS / "log_segal-police-team-vs-segal-thief-team_g01.json"
TAMPERED = GOLDENS / "log_tampered_step7.json"


def test_a_clean_log_checks_out_and_exits_zero(capsys):
    code = main(["--log", str(REFERENCE), "--check"])

    assert code == 0
    assert "Verified OK: 19 steps, 0 failed" in capsys.readouterr().out


def test_a_tampered_log_exits_non_zero_and_names_the_step(capsys):
    code = main(["--log", str(TAMPERED), "--check"])
    output = capsys.readouterr().out

    assert code == 1
    assert "TAMPERED" in output
    assert "step 7 (record 7)" in output


def test_a_malformed_log_is_reported_cleanly_not_as_a_traceback(capsys, tmp_path):
    """Exit 2 (unreadable file) is deliberately distinct from exit 1 (tampered):
    a script must be able to tell a broken file from a proven forgery."""
    broken = tmp_path / "log_broken.json"
    broken.write_text("{not json", encoding="utf-8")

    code = main(["--log", str(broken), "--check"])
    captured = capsys.readouterr()

    assert code == 2
    assert "cannot read" in captured.err
    assert "Traceback" not in captured.err


def test_a_log_with_no_records_is_a_usage_error_not_a_verdict(capsys, tmp_path):
    empty = tmp_path / "log_empty.json"
    empty.write_text('{"records": []}', encoding="utf-8")

    assert main(["--log", str(empty), "--check"]) == 2


def test_a_missing_log_is_reported_on_stderr(capsys, tmp_path):
    code = main(["--log", str(tmp_path / "absent.json"), "--check"])

    assert code == 2
    assert "no such log" in capsys.readouterr().err


def test_the_viewer_binds_to_localhost_by_default():
    """A log holds revealed nonces; nothing needs it reachable from outside."""
    args = build_parser().parse_args(["--log", "x.json"])

    assert args.host == "127.0.0.1"


def test_the_log_argument_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_serving_starts_the_viewer_on_the_requested_address(monkeypatch):
    calls = {}

    def fake_run(app, **kwargs):
        calls.update(kwargs)
        calls["app"] = app

    monkeypatch.setattr("uvicorn.run", fake_run)

    code = main(["--log", str(REFERENCE), "--port", "9123"])

    assert code == 0
    assert (calls["host"], calls["port"]) == ("127.0.0.1", 9123)
