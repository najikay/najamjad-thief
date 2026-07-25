"""Unit tests for the cross-repo core mirror tool (PLAN ADR-002)."""

from pathlib import Path


def _make_repo(root: Path, content: str) -> Path:
    (root / "src/najamjad_agent").mkdir(parents=True)
    (root / "src/najamjad_agent/core.py").write_text(content, encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    return root


def test_push_copies_manifest_files_to_sibling(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    drift = sync.run(source, sibling, push=True)
    assert drift > 0
    assert (sibling / "src/najamjad_agent/core.py").read_text() == "A = 1\n"


def test_check_reports_zero_drift_after_push(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    assert sync.run(source, sibling, push=False) == 0


def test_single_byte_drift_is_detected(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    (sibling / "src/najamjad_agent/core.py").write_text("A = 2\n", encoding="utf-8")
    assert sync.run(source, sibling, push=False) == 1


def test_role_specific_files_are_not_mirrored(load_script) -> None:
    """README/pyproject/config differ per role and must stay out of the manifest."""
    sync = load_script("sync_core")
    assert "README.md" not in sync.MANIFEST
    assert "pyproject.toml" not in sync.MANIFEST
    assert not any(entry.startswith("config") for entry in sync.MANIFEST)


def _pyproject(root: Path, name: str, line_length: int) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\n\n[tool.ruff]\nline-length = {line_length}\n',
        encoding="utf-8",
    )


def test_tooling_config_drift_is_detected(load_script, tmp_path: Path) -> None:
    """A different ruff config means the repos aren't held to one standard."""
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject(source, "najamjad-cop", 100)
    _pyproject(sibling, "najamjad-thief", 120)
    assert sync.check_tooling(source, sibling, push=False) == 1


def test_tooling_config_push_keeps_role_specific_identity(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject(source, "najamjad-cop", 100)
    _pyproject(sibling, "najamjad-thief", 120)
    sync.check_tooling(source, sibling, push=True)
    merged = (sibling / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "najamjad-thief"' in merged, "role identity preserved"
    assert "line-length = 100" in merged, "tooling mirrored"
    assert sync.check_tooling(source, sibling, push=False) == 0


def test_identical_tooling_reports_no_drift(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject(source, "najamjad-cop", 100)
    _pyproject(sibling, "najamjad-thief", 100)
    assert sync.check_tooling(source, sibling, push=False) == 0


def test_cache_dirs_are_skipped(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    (source / "src/najamjad_agent/__pycache__").mkdir()
    (source / "src/najamjad_agent/__pycache__/junk.pyc").write_bytes(b"x")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    assert not (sibling / "src/najamjad_agent/__pycache__").exists()
