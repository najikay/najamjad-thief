"""Meta-tests for the architectural rules the book disqualifies you for breaking.

Rules 1-2: cop and thief run as separate processes with separate config dirs and
zero shared runtime state — a violation disqualifies the solution "even if it
works". Rule 3: the orchestrator is the only gateway. ADR-009: every external
call passes a gatekeeper. These are structural properties, so they are tested
structurally rather than trusted to review.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src/najamjad_agent"


def _module_imports(path: Path) -> set[str]:
    """Every module this file imports, as dotted names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_no_module_imports_the_sibling_repository() -> None:
    """Sharing code at runtime across the two agents breaks Zero-Trust."""
    for path in SRC.rglob("*.py"):
        for name in _module_imports(path):
            assert "najamjad_cop" not in name, f"{path.name} imports the cop package"
            assert "najamjad_thief" not in name, f"{path.name} imports the thief package"


def test_role_config_directories_are_separate() -> None:
    """Book rule 1: config/police/ vs config/thief/, never one shared dir."""
    config = REPO / "config"
    role_dirs = {path.name for path in config.iterdir() if path.is_dir()}
    assert role_dirs & {"police", "thief"}, f"no role config directory found in {role_dirs}"
    assert not (config / "shared").exists(), "a shared runtime config dir breaks rule 2"


def test_the_domain_never_imports_the_network_layer() -> None:
    """The game rules must stay testable without a socket in sight."""
    for path in (SRC / "domain").rglob("*.py"):
        for name in _module_imports(path):
            assert ".net." not in name and not name.endswith(".net"), (
                f"domain/{path.name} imports the net layer"
            )


def test_the_domain_never_imports_an_llm_provider() -> None:
    """Book rule 25: the LLM must not be able to reach move selection."""
    for path in (SRC / "domain").rglob("*.py"):
        for name in _module_imports(path):
            assert "llm" not in name.split("."), f"domain/{path.name} imports the llm layer"
            assert "anthropic" not in name, f"domain/{path.name} imports an LLM SDK"
            assert "openai" not in name, f"domain/{path.name} imports an LLM SDK"


def test_only_the_client_talks_to_the_opponent() -> None:
    """One egress path means one place the gatekeeper has to be applied.

    Checks imports, not prose — a docstring may name FastMCP while explaining
    why the module deliberately does not use it.
    """
    allowed = {"mcp_client.py", "mcp_server.py"}
    for path in SRC.rglob("*.py"):
        if path.name in allowed:
            continue
        for name in _module_imports(path):
            assert not name.startswith("fastmcp"), f"{path.name} imports fastmcp directly"
            assert not name.startswith("httpx"), f"{path.name} opens its own HTTP client"


def test_the_client_routes_every_send_through_the_gatekeeper() -> None:
    """ADR-009: no direct API call may bypass the limiter."""
    source = (SRC / "net/mcp_client.py").read_text(encoding="utf-8")
    assert "self._gatekeeper.execute" in source
    tree = ast.parse(source)
    send = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "send"
    )
    calls = ast.dump(send)
    assert "_gatekeeper" in calls, "send() must go through the gatekeeper"


def test_mcp_tools_contain_no_game_logic() -> None:
    """Tools validate and enqueue; anything else belongs to the orchestrator."""
    source = (SRC / "net/mcp_server.py").read_text(encoding="utf-8")
    for forbidden in ("BeliefGrid", "apply_move", "ScoreTable", "evaluate_capture"):
        assert forbidden not in source, f"mcp_server.py contains game logic ({forbidden})"


def test_every_net_module_stays_within_the_file_budget() -> None:
    """The 150-line rule applies here too; splitting beats compressing."""
    for path in (SRC / "net").glob("*.py"):
        code_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert len(code_lines) <= 150, f"{path.name} has {len(code_lines)} lines"
