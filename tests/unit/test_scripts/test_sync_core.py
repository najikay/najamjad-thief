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


def _pyproject_with_deps(root: Path, name: str, dev: str) -> None:
    """A pyproject whose dev-dependency group is the thing under test."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\ndescription = "the {name} agent"\n'
        f'dependencies = ["pydantic>=2.7"]\n\n'
        f"[dependency-groups]\ndev = [{dev}]\n\n[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )


def test_a_dev_dependency_present_in_only_one_repo_is_drift(load_script, tmp_path: Path) -> None:
    """The quiet failure: a test imports it, passes here, fails in the twin."""
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject_with_deps(source, "najamjad-cop", '"pytest>=8.2", "pyyaml>=6.0"')
    _pyproject_with_deps(sibling, "najamjad-thief", '"pytest>=8.2"')

    assert sync.check_tooling(source, sibling, push=False) == 1


def test_pushing_mirrors_dev_dependencies_but_keeps_the_twins_identity(
    load_script, tmp_path: Path
) -> None:
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject_with_deps(source, "najamjad-cop", '"pytest>=8.2", "pyyaml>=6.0"')
    _pyproject_with_deps(sibling, "najamjad-thief", '"pytest>=8.2"')

    sync.check_tooling(source, sibling, push=True)
    merged = (sibling / "pyproject.toml").read_text(encoding="utf-8")

    assert "pyyaml>=6.0" in merged, "dev dependencies mirrored"
    assert 'name = "najamjad-thief"' in merged, "role identity preserved"
    assert 'description = "the najamjad-thief agent"' in merged
    assert "najamjad-cop" not in merged
    assert sync.check_tooling(source, sibling, push=False) == 0


def test_a_runtime_dependency_difference_is_drift(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    _pyproject_with_deps(source, "najamjad-cop", '"pytest>=8.2"')
    _pyproject_with_deps(sibling, "najamjad-thief", '"pytest>=8.2"')
    twin = sibling / "pyproject.toml"
    twin.write_text(
        twin.read_text(encoding="utf-8").replace("pydantic>=2.7", "pydantic>=2.0"),
        encoding="utf-8",
    )

    assert sync.check_tooling(source, sibling, push=False) == 1


def test_a_name_inside_a_tool_section_cannot_overwrite_the_project_identity(
    load_script, tmp_path: Path
) -> None:
    """Role-specific lines are matched by position; keying on the field name
    would let a second `name =` anywhere in the file capture the project's."""
    sync = load_script("sync_core")
    source, sibling = _make_repo(tmp_path / "cop", "A = 1\n"), tmp_path / "thief"
    sibling.mkdir()
    body = '[project]\nname = "{n}"\n\n[tool.thing]\nname = "shared-tool-name"\nx = {x}\n'
    (source / "pyproject.toml").write_text(body.format(n="najamjad-cop", x=1), encoding="utf-8")
    (sibling / "pyproject.toml").write_text(body.format(n="najamjad-thief", x=2), encoding="utf-8")

    sync.check_tooling(source, sibling, push=True)
    merged = (sibling / "pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "najamjad-thief"' in merged
    assert 'name = "shared-tool-name"' in merged
    assert "x = 1" in merged


def test_cache_dirs_are_skipped(load_script, tmp_path: Path) -> None:
    sync = load_script("sync_core")
    source = _make_repo(tmp_path / "cop", "A = 1\n")
    (source / "src/najamjad_agent/__pycache__").mkdir()
    (source / "src/najamjad_agent/__pycache__/junk.pyc").write_bytes(b"x")
    sibling = tmp_path / "thief"
    sibling.mkdir()
    sync.run(source, sibling, push=True)
    assert not (sibling / "src/najamjad_agent/__pycache__").exists()
