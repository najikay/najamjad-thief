"""Unit tests for the file-size CI gate (guidelines §3.2 semantics)."""

from pathlib import Path


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_blank_and_comment_lines_do_not_count(load_script, tmp_path: Path) -> None:
    gate = load_script("check_file_sizes")
    body = "x = 1\n\n# a comment line\ny = 2\n   # indented comment\n\nz = 3\n"
    assert gate.count_code_lines(_write(tmp_path, body)) == 3


def test_docstrings_do_not_count(load_script, tmp_path: Path) -> None:
    gate = load_script("check_file_sizes")
    body = '"""Module docstring\nspanning three lines.\n"""\n\ndef f() -> int:\n    """Doc."""\n    return 1\n'
    assert gate.count_code_lines(_write(tmp_path, body)) == 2


def test_file_at_121_code_lines_is_warn_not_fail(load_script, tmp_path: Path) -> None:
    """121 code lines: over the internal budget, under the course hard cap."""
    gate = load_script("check_file_sizes")
    path = _write(tmp_path, "\n".join(f"v{i} = {i}" for i in range(121)) + "\n")
    count = gate.count_code_lines(path)
    assert gate.WARN_CAP < count <= gate.HARD_CAP


def test_file_at_151_code_lines_breaks_hard_cap(load_script, tmp_path: Path) -> None:
    gate = load_script("check_file_sizes")
    path = _write(tmp_path, "\n".join(f"v{i} = {i}" for i in range(151)) + "\n")
    assert gate.count_code_lines(path) > gate.HARD_CAP


def test_caps_match_course_rule(load_script) -> None:
    gate = load_script("check_file_sizes")
    assert gate.HARD_CAP == 150
    assert gate.WARN_CAP == 120
