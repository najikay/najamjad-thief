"""The local gate runner must not drift from CI.

`check_all.py` exists so one command gives one verdict. That is only worth
anything if a local pass means CI will pass — the moment CI checks something the
runner skips, "all gates passed" becomes a claim nobody verified, which is the
exact failure this script was written to prevent.

These tests hold the two lists together.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def ci_run_commands() -> list[str]:
    """Every `run:` body from the CI quality job."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step["run"].strip() for step in document["jobs"]["quality"]["steps"] if "run" in step]


def test_every_ci_command_is_covered_by_the_local_runner(load_script):
    """A gate CI runs and the runner skips would make a local pass meaningless."""
    runner = load_script("check_all")
    local = {" ".join(command) for _name, command, _slow in runner.GATES}
    local.add("uv sync --frozen")  # dependency install, not a gate

    uncovered = []
    for command in ci_run_commands():
        if command.startswith("for f in"):
            continue  # the structure step, covered by its own test below
        normalised = command.replace("uv run pytest tests/", "uv run pytest tests/ -q")
        if normalised not in local:
            uncovered.append(command)

    assert not uncovered, f"CI runs gates the local runner skips: {uncovered}"


def test_the_runner_checks_the_same_mandated_files_as_ci(load_script):
    runner = load_script("check_all")
    structure = next(cmd for cmd in ci_run_commands() if cmd.startswith("for f in"))

    for name in runner.MANDATED_FILES:
        assert name in structure, f"{name} is checked locally but not by CI"


def test_every_mandated_file_actually_exists(load_script):
    runner = load_script("check_all")

    assert runner.missing_mandated_files() == []


def test_a_missing_mandated_file_is_reported(load_script, monkeypatch):
    """Proves the check can fail, not just that it currently passes."""
    runner = load_script("check_all")
    monkeypatch.setattr(runner, "MANDATED_FILES", ("docs/PRD.md", "docs/does-not-exist.md"))

    assert runner.missing_mandated_files() == ["docs/does-not-exist.md"]


def action_pin(action: str) -> str:
    """The ref `ci.yml` pins for one action."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    uses = [step["uses"] for step in document["jobs"]["quality"]["steps"] if "uses" in step]
    return next(ref for ref in uses if ref.startswith(action + "@"))


@pytest.mark.parametrize(
    ("action", "minimum"), [("actions/checkout", 5), ("astral-sh/setup-uv", 6)]
)
def test_ci_actions_target_a_supported_node_runtime(action, minimum):
    """node20 actions are force-migrated by GitHub and will eventually break."""
    pin = action_pin(action)
    major = int(pin.rsplit("@v", 1)[1].split(".")[0])

    assert major >= minimum, f"{pin} predates the node24 runtime"


def test_setup_uv_is_pinned_to_an_exact_version():
    """From v8, setup-uv publishes immutable release tags only — there is no
    moving `v8`/`v9` to follow. `@v9` looks reasonable, resolves to nothing, and
    fails at "Set up job" before a single gate runs. Learned the hard way.
    """
    version = action_pin("astral-sh/setup-uv").rsplit("@v", 1)[1]

    assert version.count(".") == 2, "setup-uv >= v8 must be pinned as vX.Y.Z"


def test_every_pinned_action_uses_a_version_ref():
    """A branch ref would make the pipeline depend on someone else's `main`."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    for step in document["jobs"]["quality"]["steps"]:
        if "uses" in step:
            assert "@v" in step["uses"], f"{step['uses']} is not pinned to a version"
