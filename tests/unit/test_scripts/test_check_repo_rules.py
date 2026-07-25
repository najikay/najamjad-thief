"""Unit tests for the repo-rules CI gate (uv-only, silent-except, secrets).

repo-rules-gate-fixtures: this file deliberately contains the forbidden
patterns it asserts on, so the gate skips scanning its own content.
"""

from pathlib import Path


def _scan_one(gate, root: Path, name: str, body: str) -> list[str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return gate._scan(path, root)


def test_pip_in_markdown_prose_is_allowed(load_script, tmp_path: Path) -> None:
    """Prose describing the prohibition is not a violation (T-0210 semantics)."""
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "doc.md", "The rule forbids `pip install` anywhere.\n")
    assert issues == []


def test_pip_inside_markdown_fence_is_flagged(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "doc.md", "```bash\npip install foo\n```\n")
    assert any("UV-ONLY" in issue for issue in issues)


def test_fenced_third_party_quote_marker_is_allowed(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    body = "```bash\npython -m police_thief peer  # third-party-quote-ok\n```\n"
    assert _scan_one(gate, tmp_path, "doc.md", body) == []


def test_pip_in_python_source_is_flagged(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "tool.py", 'CMD = "pip install requests"\n')
    assert any("UV-ONLY" in issue for issue in issues)


def test_bare_python_dash_m_is_flagged(load_script, tmp_path: Path) -> None:
    """A bare interpreter escapes the locked environment — the rule's point."""
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "doc.md", "```bash\npython -m najamjad_agent.replay\n```\n")
    assert any("UV-ONLY" in issue for issue in issues)


def test_uv_run_python_dash_m_is_allowed(load_script, tmp_path: Path) -> None:
    """`uv run python -m mod` IS uv-only tooling; flagging it was a false positive."""
    gate = load_script("check_repo_rules")
    body = "```bash\nuv run python -m najamjad_agent.replay --log x.json\n```\n"
    assert _scan_one(gate, tmp_path, "doc.md", body) == []


def test_uv_run_does_not_launder_a_pip_install(load_script, tmp_path: Path) -> None:
    """The `uv run` exemption must not become a way to smuggle pip past the gate."""
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "doc.md", "```bash\nuv run python -m pip install x\n```\n")
    assert any("UV-ONLY" in issue for issue in issues)


def test_pipeline_word_is_not_a_false_positive(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    assert _scan_one(gate, tmp_path, "doc.md", "Our CI pipeline installs via uv.\n") == []


def test_silent_except_pass_is_flagged(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    body = "try:\n    risky()\nexcept ValueError:\n    pass\n"
    issues = _scan_one(gate, tmp_path, "module.py", body)
    assert any("SILENT-EXCEPT" in issue for issue in issues)


def test_logged_exception_handler_passes(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    body = "try:\n    risky()\nexcept ValueError:\n    logger.warning('boom')\n"
    assert _scan_one(gate, tmp_path, "module.py", body) == []


def test_tracked_secret_filename_is_flagged(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "credentials.json", "{}")
    assert any("SECRET-FILE" in issue for issue in issues)


def test_credential_like_content_is_flagged(load_script, tmp_path: Path) -> None:
    gate = load_script("check_repo_rules")
    issues = _scan_one(gate, tmp_path, "notes.txt", "key = sk-ant-api03-abcdef\n")
    assert any("SECRET-CONTENT" in issue for issue in issues)


def test_header_fixture_marker_exempts_planted_patterns(load_script, tmp_path: Path) -> None:
    """This test file itself relies on the exemption — lock its behaviour."""
    gate = load_script("check_repo_rules")
    body = f'"""Doc.\n\n{gate.FIXTURE_MARKER}: planted patterns below.\n"""\nCMD = "pip install x"\n'
    assert _scan_one(gate, tmp_path, "fixtures.py", body) == []


def test_fixture_marker_below_the_header_does_not_exempt(load_script, tmp_path: Path) -> None:
    """The escape hatch must not be hideable deep inside a real module."""
    gate = load_script("check_repo_rules")
    filler = "\n".join(f"x{i} = {i}" for i in range(gate.FIXTURE_HEADER_LINES + 5))
    body = f'{filler}\n# {gate.FIXTURE_MARKER}\nCMD = "pip install x"\n'
    issues = _scan_one(gate, tmp_path, "sneaky.py", body)
    assert any("UV-ONLY" in issue for issue in issues)
