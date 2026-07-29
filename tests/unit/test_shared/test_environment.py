"""Loading `.env` (T-2428).

A gap rather than a bug: `.env-example` told the operator to copy the file and
fill in real values, `.gitignore` protected it, the README referred to it — and
nothing in the codebase ever read it. A key pasted into `.env` had exactly the
effect of no key at all, silently, because a vendor without credentials is
skipped rather than reported broken.

The contract worth pinning is the precedence, not the parsing.
"""

from najamjad_agent.shared.environment import load_env


def env_file(tmp_path, body: str):
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_key_in_the_file_reaches_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert load_env(env_file(tmp_path, "DEEPSEEK_API_KEY=from-file\n")) is True

    import os

    assert os.environ["DEEPSEEK_API_KEY"] == "from-file"


def test_an_exported_variable_beats_the_file(tmp_path, monkeypatch):
    """The whole contract.

    A variable exported in the shell, or injected by CI, is a deliberate act by
    whoever ran the process. A checked-out file must not quietly replace it —
    which is also what keeps CI honest, since CI sets secrets as environment
    variables and ships no `.env` at all.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")

    load_env(env_file(tmp_path, "DEEPSEEK_API_KEY=from-file\n"))

    import os

    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"


def test_a_missing_file_is_the_normal_case_not_an_error(tmp_path):
    """Fresh clones and CI have no `.env`; that must not raise."""
    assert load_env(tmp_path / "absent.env") is False


def test_the_real_entry_point_loads_it():
    """`build_sdk` is the single door every command goes through, so the load
    belongs there rather than in each caller."""
    import inspect

    from najamjad_agent.sdk import bootstrap

    assert "load_env()" in inspect.getsource(bootstrap.build_sdk)
