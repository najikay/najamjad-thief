"""Match archiving — and the one thing it must never put in a zip.

An archive gets shared: with a grader, sometimes with an opponent settling a
dispute. A missing log is an inconvenience; a credential inside a bundle that
leaves the machine is an incident. So the secret-exclusion tests here matter
more than the completeness ones.
"""

import json
import zipfile

import pytest

from najamjad_agent.reporting.archive import build_archive, is_secret


@pytest.fixture()
def workspace(tmp_path):
    """A finished match's leftovers, secrets included."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "log_game_g01.json").write_text('{"records": []}', encoding="utf-8")
    (artifacts / "result_game.json").write_text("{}", encoding="utf-8")
    events = tmp_path / "events.jsonl"
    events.write_text('{"event": "game.started"}\n', encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "token.json").write_text('{"refresh_token": "SHOULD NEVER SHIP"}', encoding="utf-8")
    (secrets / "credentials.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_the_archive_contains_the_match_evidence(workspace, tmp_path):
    report = build_archive(
        tmp_path / "out" / "match.zip",
        {"artifacts": workspace / "artifacts", "events": workspace / "events.jsonl"},
    )

    assert report.path.exists()
    assert "artifacts/log_game_g01.json" in report.included
    assert "events/events.jsonl" in report.included
    assert report.file_count == 3


def test_secrets_are_refused_and_recorded(workspace, tmp_path):
    """Not silently dropped — an operator must see what was withheld."""
    report = build_archive(
        tmp_path / "match.zip",
        {"artifacts": workspace / "artifacts", "secrets": workspace / "secrets"},
    )

    assert report.excluded_secrets == ["secrets/credentials.json", "secrets/token.json"]
    assert not any("token" in name for name in report.included)


def test_no_secret_byte_reaches_the_zip(workspace, tmp_path):
    """The assertion that actually matters: scan the archive, not the report."""
    destination = tmp_path / "match.zip"
    build_archive(destination, {"secrets": workspace / "secrets", "a": workspace / "artifacts"})

    with zipfile.ZipFile(destination) as bundle:
        blob = b"".join(bundle.read(name) for name in bundle.namelist())

    assert b"SHOULD NEVER SHIP" not in blob
    assert not any("token.json" in name for name in zipfile.ZipFile(destination).namelist())


@pytest.mark.parametrize(
    "name", ["token.json", "credentials.json", ".env", "server.pem", "private.key"]
)
def test_every_secret_shape_is_recognised(tmp_path, name):
    assert is_secret(tmp_path / name) is True


@pytest.mark.parametrize("name", ["log_game_g01.json", "events.jsonl", "board.png"])
def test_ordinary_evidence_is_not_mistaken_for_a_secret(tmp_path, name):
    assert is_secret(tmp_path / name) is False


def test_a_missing_source_is_noted_rather_than_fatal(workspace, tmp_path):
    """A match with no screenshots must still produce an archive."""
    report = build_archive(
        tmp_path / "match.zip",
        {"artifacts": workspace / "artifacts", "screenshots": workspace / "nope"},
    )

    assert report.missing_sources == ["screenshots"]
    assert report.path.exists()


def test_the_manifest_is_written_inside_the_archive(workspace, tmp_path):
    destination = tmp_path / "match.zip"
    build_archive(destination, {"artifacts": workspace / "artifacts"})

    with zipfile.ZipFile(destination) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))

    assert manifest["file_count"] == 2
    assert "artifacts/result_game.json" in manifest["files"]


def test_a_single_file_source_keeps_its_name(workspace, tmp_path):
    report = build_archive(tmp_path / "match.zip", {"events": workspace / "events.jsonl"})

    assert report.included == ["events/events.jsonl"]


def test_cache_directories_are_skipped(tmp_path):
    source = tmp_path / "workspace"
    (source / "__pycache__").mkdir(parents=True)
    (source / "__pycache__" / "x.pyc").write_bytes(b"junk")
    (source / "keep.json").write_text("{}", encoding="utf-8")

    report = build_archive(tmp_path / "match.zip", {"w": source})

    assert report.included == ["w/keep.json"]
