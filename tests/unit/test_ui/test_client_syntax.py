"""Syntax-check the browser modules.

The Python suite cannot see inside the client, so a typo there stays invisible
until someone opens the page — which for us would mean during a match. Node is
already present on CI runners, and parsing every module as an ES module is the
cheapest check that catches the class of bug the panel renderers hit twice: a
function declared under a name that was already taken, and a stray edit that
leaves a module unparseable.

Skipped rather than failed where node is unavailable, so a clean clone without
it still runs the suite.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "najamjad_agent"
SCRIPTS = sorted((PACKAGE / "ui" / "static").glob("*.js")) + sorted(
    (PACKAGE / "replay" / "static").glob("*.js")
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_every_client_module_parses(script):
    result = subprocess.run(
        ["node", "--input-type=module", "--check"],
        input=script.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"{script.name} does not parse:\n{result.stderr}"


def test_the_check_would_actually_reject_broken_source(tmp_path):
    """Otherwise the test above could pass by never running node properly."""
    result = subprocess.run(
        ["node", "--input-type=module", "--check"],
        input="function broken( {\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0


def test_there_are_client_modules_to_check():
    """A glob that silently matched nothing would make this file decorative."""
    assert len(SCRIPTS) >= 4
