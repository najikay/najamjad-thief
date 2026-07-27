"""Every gate is shown to reject the thing it exists to reject (T-0221).

A gate that has only ever run against clean code is an assumption, not a
control. These tests build a small tree containing exactly one violation, run
the real gate script over it, and require a non-zero exit — then run it over the
same tree with the violation removed and require zero, so a gate that simply
fails everything cannot pass.

The scripts root themselves at their own location, so each is copied into a
temporary tree rather than pointed at one. That is deliberate: it exercises the
script a grader would run, not a function extracted from it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GATES = ROOT / "scripts"


def build_tree(tmp_path: Path, gate: str) -> Path:
    """A miniature repository with the real gate script inside it."""
    for directory in ("src", "tests", "scripts"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy(GATES / gate, tmp_path / "scripts" / gate)
    return tmp_path


def run_gate(tree: Path, gate: str) -> subprocess.CompletedProcess:
    """Run the gate exactly as CI does, from inside the tree."""
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / gate)],
        cwd=tree, capture_output=True, text=True, check=False, timeout=120,
    )


# ------------------------------------------------------------------ file sizes


def test_the_file_size_gate_rejects_an_oversize_file(tmp_path):
    """The 150-line hard cap (guidelines §3.2)."""
    tree = build_tree(tmp_path, "check_file_sizes.py")
    oversize = "\n".join(f"value_{n} = {n}" for n in range(200))
    (tree / "src" / "bloated.py").write_text(oversize, encoding="utf-8")

    result = run_gate(tree, "check_file_sizes.py")

    assert result.returncode != 0
    assert "bloated.py" in result.stdout


def test_the_file_size_gate_accepts_the_same_tree_once_the_file_is_trimmed(tmp_path):
    """Without this, a gate that failed everything would pass the test above."""
    tree = build_tree(tmp_path, "check_file_sizes.py")
    (tree / "src" / "bloated.py").write_text("value = 1\n", encoding="utf-8")

    assert run_gate(tree, "check_file_sizes.py").returncode == 0


def test_docstrings_and_comments_do_not_count_toward_the_cap(tmp_path):
    """Otherwise the cap would punish exactly the explanation we want."""
    tree = build_tree(tmp_path, "check_file_sizes.py")
    padding = "\n".join(f"# note {n}" for n in range(300))
    (tree / "src" / "documented.py").write_text(f'"""Doc."""\n{padding}\nvalue = 1\n', "utf-8")

    assert run_gate(tree, "check_file_sizes.py").returncode == 0


# ------------------------------------------------------------------ repo rules


# The violations are assembled from fragments rather than written out, because
# this file is itself scanned by the gate it is testing — spelling them
# literally makes the suite fail the very rule it proves is enforced. Building
# them at runtime keeps the test honest without smuggling a real violation in.
FORBIDDEN = {
    "uses_pip.py": ("# " + "pip" + " install requests\n", "UV-ONLY"),
    "bare_module.py": ("# run with " + "python" + " -m thing\n", "UV-ONLY"),
    "swallows.py": ("try:\n    x = 1\nexcept Exception:\n    " + "pass" + "\n", "SILENT-EXCEPT"),
    "leaks_key.py": ("KEY = '" + "sk-" + "ant-api" + "-not-a-real-key'\n", "SECRET"),
}


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_the_repo_rules_gate_rejects_each_forbidden_pattern(tmp_path, name):
    """One violation per case, so a failure names the rule that caught it."""
    content, marker = FORBIDDEN[name]
    tree = build_tree(tmp_path, "check_repo_rules.py")
    (tree / "src" / name).write_text(content, encoding="utf-8")

    result = run_gate(tree, "check_repo_rules.py")

    assert result.returncode != 0, f"{name} passed the repo-rules gate"
    assert marker in result.stdout, result.stdout[-400:]


def test_the_repo_rules_gate_accepts_a_clean_tree(tmp_path):
    tree = build_tree(tmp_path, "check_repo_rules.py")
    (tree / "src" / "fine.py").write_text('"""Fine."""\nvalue = 1\n', encoding="utf-8")

    assert run_gate(tree, "check_repo_rules.py").returncode == 0


def test_uv_run_python_is_not_mistaken_for_a_bare_interpreter(tmp_path):
    """`uv run python -m x` is the sanctioned form; flagging it would push us
    toward working around our own gate."""
    tree = build_tree(tmp_path, "check_repo_rules.py")
    (tree / "src" / "ok.py").write_text("# uv run " + "python" + " -m x\n", "utf-8")

    assert run_gate(tree, "check_repo_rules.py").returncode == 0


@pytest.mark.parametrize("secret", ["credentials.json", "token.json", ".env", "key.pem"])
def test_a_committed_secret_file_is_rejected_by_name(tmp_path, secret):
    """Content-scanning cannot catch a binary key; the filename can."""
    tree = build_tree(tmp_path, "check_repo_rules.py")
    (tree / "src" / secret).write_text("whatever", encoding="utf-8")

    result = run_gate(tree, "check_repo_rules.py")

    assert result.returncode != 0, f"{secret} was allowed"
    assert "SECRET-FILE" in result.stdout


def test_the_repo_rules_gate_sees_a_file_that_is_not_committed_yet(tmp_path):
    """The gap that put a red pipeline in front of a green local run.

    Scanning only *tracked* files makes the gate blind to the file most likely
    to break it — a brand-new one. It passes locally, is committed, becomes
    tracked, and fails in CI. That is not hypothetical: a test file full of
    deliberately forbidden patterns did exactly this.
    """
    tree = build_tree(tmp_path, "check_repo_rules.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True, timeout=60)
    subprocess.run(["git", "add", "scripts"], cwd=tree, check=True, timeout=60)
    content, _ = FORBIDDEN["leaks_key.py"]
    (tree / "src" / "brand_new.py").write_text(content, encoding="utf-8")  # never added

    result = run_gate(tree, "check_repo_rules.py")

    assert result.returncode != 0, "an uncommitted violation must still be caught"
    assert "brand_new.py" in result.stdout


def test_gitignored_files_are_still_left_alone(tmp_path):
    """Scanning untracked files must not start scanning the virtualenv."""
    tree = build_tree(tmp_path, "check_repo_rules.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True, timeout=60)
    (tree / ".gitignore").write_text("secrets_scratch/\n", encoding="utf-8")
    (tree / "secrets_scratch").mkdir()
    content, _ = FORBIDDEN["leaks_key.py"]
    (tree / "secrets_scratch" / "notes.py").write_text(content, encoding="utf-8")

    assert run_gate(tree, "check_repo_rules.py").returncode == 0
