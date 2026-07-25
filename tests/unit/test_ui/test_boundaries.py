"""Meta-tests: the architecture rules the dashboard must not drift out of.

Two rules, both from hard-won lessons. The UI reaches the agent only through the
SDK, so "the dashboard cannot show something the rules forbid" is structural
rather than a habit. And the client never polls, because A6's timer-driven UI
was both the clunky one and the one that missed updates.
"""

import ast
import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[3] / "src" / "najamjad_agent" / "ui"
STATIC = UI / "static"
ALLOWED_INTERNAL = {"sdk"}


def imported_packages(path: Path) -> set[str]:
    """Sibling packages a module reaches into (e.g. 'domain', 'sdk').

    A level-1 relative import stays inside `ui` and is none of this test's
    business; level 2 or more climbs to `najamjad_agent`, and the first
    component there is the package being reached into.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level >= 2:
            names = [node.module] if node.module else [alias.name for alias in node.names]
            found.update(name.split(".")[0] for name in names if name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("najamjad_agent."):
                    found.add(alias.name.split(".")[1])
    return found


@pytest.mark.parametrize("module", sorted(UI.glob("*.py")), ids=lambda path: path.name)
def test_the_ui_reaches_the_agent_only_through_the_sdk(module):
    internal = imported_packages(module)

    assert internal <= ALLOWED_INTERNAL, (
        f"{module.name} imports {sorted(internal - ALLOWED_INTERNAL)}; "
        "the UI may only import najamjad_agent.sdk (FR-UI-4)"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from ..domain.board import Board\n", {"domain"}),
        ("from .. import strategy\n", {"strategy"}),
        ("import najamjad_agent.net.mcp_server\n", {"net"}),
        ("from .frames import validate_frame\n", set()),
    ],
)
def test_the_meta_test_catches_every_way_around_the_boundary(tmp_path, source, expected):
    offender = tmp_path / "sneaky.py"
    offender.write_text(source, encoding="utf-8")

    assert imported_packages(offender) == expected


@pytest.mark.parametrize("script", sorted(STATIC.glob("*.js")), ids=lambda path: path.name)
def test_the_client_never_polls_on_a_timer(script):
    source = script.read_text(encoding="utf-8")

    assert "setInterval" not in source, f"{script.name} polls; updates arrive over the socket"


def test_the_only_timer_in_the_client_is_the_reconnect_backoff():
    source = (STATIC / "dashboard.js").read_text(encoding="utf-8")

    assert source.count("setTimeout") == 1
    assert "setTimeout(connect, backoff)" in source


def test_a_dropped_socket_marks_the_panels_stale_rather_than_lying():
    """Stale numbers that still look live are worse than an obvious gap."""
    source = (STATIC / "dashboard.js").read_text(encoding="utf-8")

    assert "reconnecting in" in source
    assert "classList.toggle('stale'" in source
    assert "socket.onclose" in source


@pytest.mark.parametrize("script", sorted(STATIC.glob("*.js")), ids=lambda path: path.name)
def test_no_module_declares_the_same_function_twice(script):
    """A redeclared function silently wins over the first — the later one
    replaces it, and whatever called the original starts doing something else.
    """
    names = re.findall(r"^(?:export )?function (\w+)", script.read_text(encoding="utf-8"), re.M)

    duplicates = {name for name in names if names.count(name) > 1}

    assert not duplicates, f"{script.name} declares {sorted(duplicates)} more than once"


def test_the_page_loads_its_client_as_a_module():
    page = (STATIC / "index.html").read_text(encoding="utf-8")

    assert 'type="module" src="/static/dashboard.js"' in page


@pytest.mark.parametrize(
    "panel",
    ["board", "banner", "transcript", "negotiation", "budget", "gatekeepers", "report", "events"],
)
def test_every_panel_the_client_paints_exists_in_the_page(panel):
    page = (STATIC / "index.html").read_text(encoding="utf-8")

    assert f'id="{panel}"' in page
