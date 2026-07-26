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



def test_a_file_deleted_in_the_source_is_reported_as_an_orphan(load_script, tmp_path: Path):
    """Copying is not mirroring: a rename leaves a stale twin behind, and two
    test modules sharing a basename break pytest collection outright."""
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    stale = sibling / "src/najamjad_agent/gone.py"
    stale.write_text("# left over from a rename\n", encoding="utf-8")

    drift = sync.run(source, sibling, push=False)

    assert drift == 1
    assert sync.orphans(source, sibling) == [Path("src/najamjad_agent/gone.py")]


def test_pushing_removes_the_orphan(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    stale = sibling / "src/najamjad_agent/gone.py"
    stale.write_text("# left over\n", encoding="utf-8")

    sync.run(source, sibling, push=True)

    assert not stale.exists()
    assert sync.run(source, sibling, push=False) == 0


def test_files_outside_the_manifest_are_never_removed(load_script, tmp_path: Path) -> None:
    """README and config are role-specific — deleting them would be a disaster."""
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    (sibling / "README.md").write_text("# thief\n", encoding="utf-8")
    (sibling / "config").mkdir()
    (sibling / "config" / "game.toml").write_text("version = '1.00'\n", encoding="utf-8")

    sync.run(source, sibling, push=True)

    assert (sibling / "README.md").exists()
    assert (sibling / "config" / "game.toml").exists()


def test_cache_dirs_are_skipped(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    (source / "src/najamjad_agent/__pycache__").mkdir()
    (source / "src/najamjad_agent/__pycache__/junk.pyc").write_bytes(b"x")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    assert not (sibling / "src/najamjad_agent/__pycache__").exists()
