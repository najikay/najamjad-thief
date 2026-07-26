"""Meta-tests: the CLI is a keyboard, not a brain.

Guidelines §5.3 put every business decision behind the SDK. That is only true
if it is enforced, because the CLI is exactly where a quick conditional is most
tempting to add. Each verb should read as: parse arguments, make one SDK call,
turn the result into output and an exit code.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "najamjad_agent"
CLI = PACKAGE / "cli.py"
ALLOWED_INTERNAL = {"sdk", "shared", "replay"}
TREE = ast.parse(CLI.read_text(encoding="utf-8"))
VERBS = {"peer", "preflight", "replay", "archive", "version"}


def verb_functions() -> dict[str, ast.FunctionDef]:
    """The command functions typer exposes."""
    return {
        node.name: node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in VERBS
    }


def test_every_declared_verb_exists():
    assert set(verb_functions()) == VERBS


@pytest.mark.parametrize("name", sorted(VERBS))
def test_a_verb_holds_no_loops(name):
    """Iteration over domain data is logic; a verb may only loop to print."""
    body = verb_functions()[name]

    loops = [node for node in ast.walk(body) if isinstance(node, ast.While)]

    assert not loops, f"{name}() contains a while loop"


@pytest.mark.parametrize("name", sorted(VERBS))
def test_a_verb_stays_small_enough_to_read_at_a_glance(name):
    """A long verb is one that started deciding things."""
    body = verb_functions()[name]

    statements = [node for node in body.body if not isinstance(node, ast.Expr | ast.Import)]

    assert len(statements) <= 8, f"{name}() has {len(statements)} statements; delegate more"


def test_the_cli_reaches_the_agent_only_through_permitted_packages():
    """`sdk` for business operations; `shared` for the version constant;
    `replay` for the viewer entry point, which is a consumer like the CLI."""
    reached = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module:
            reached.add(node.module.split(".")[0])

    assert reached <= ALLOWED_INTERNAL, f"CLI imports {sorted(reached - ALLOWED_INTERNAL)}"


@pytest.mark.parametrize(
    "forbidden", ["domain", "strategy", "negotiation", "reporting", "llm", "protocol", "net"]
)
def test_the_cli_never_imports_an_internal_subsystem(forbidden):
    """Importing the domain directly is how a CLI grows a second rulebook."""
    assert f"from .{forbidden}" not in CLI.read_text(encoding="utf-8")


def test_the_meta_test_would_notice_a_smuggled_import(tmp_path):
    """Otherwise this file could pass by checking nothing."""
    offender = tmp_path / "cli.py"
    offender.write_text("from .domain.board import Board\n", encoding="utf-8")

    reached = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(offender.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module
    }

    assert reached == {"domain"}
    assert not reached <= ALLOWED_INTERNAL


def test_the_console_script_is_declared_and_named_after_this_repo():
    """T-2015. The name is role-specific; the thief once shipped a
    `najamjad-cop` command because a sync mirrored it verbatim."""
    import tomllib

    pyproject = tomllib.loads((PACKAGE.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert list(scripts) == [pyproject["project"]["name"]]
    assert scripts[pyproject["project"]["name"]] == "najamjad_agent.cli:main"


def test_the_entry_point_target_exists():
    """A declared entry point that cannot be imported fails only at run time."""
    from najamjad_agent.cli import main

    assert callable(main)


def test_the_exit_code_contract_is_documented():
    """Scripts depend on 0/1/2 meaning different things; say so in the module."""
    docstring = ast.get_docstring(TREE) or ""

    assert "0" in docstring and "1" in docstring and "2" in docstring
