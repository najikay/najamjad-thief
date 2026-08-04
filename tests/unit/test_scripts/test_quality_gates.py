"""The project's own quality claims, asserted rather than believed (T-2121..T-2124).

Every number in the README and the report is checkable. These tests make the
claims fail loudly when they stop being true, because a stale quality claim in a
graded document is worse than no claim.
"""

import subprocess
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "najamjad_agent"


def test_the_coverage_floor_is_configured_and_enforced():
    """T-2121. A floor nobody enforces is a preference."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["coverage"]["report"]["fail_under"] >= 85


def test_the_coverage_omit_list_is_honest():
    """T-2122. Omitting a module is how a project buys coverage it has not
    earned. Only non-Python UI assets and the test tree may be excluded — every
    integration seam is covered through in-process fakes instead."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    omit = set(config["tool"]["coverage"]["run"]["omit"])

    allowed = {"*/tests/*", "src/najamjad_agent/ui/static/*"}
    assert omit <= allowed, f"unjustified omissions: {sorted(omit - allowed)}"


@pytest.mark.parametrize(
    "seam", ["net/mcp_client.py", "net/mcp_server.py", "reporting/gmail_sender.py", "net/tunnel.py"]
)
def test_every_integration_seam_is_in_the_measured_tree(seam):
    """The seams most tempting to omit are exactly the ones that must not be."""
    assert (SRC / seam).exists()


def test_the_core_is_byte_identical_across_both_repos():
    """T-2124. The two repos ship one core; drift means one of them is untested."""
    sibling = ROOT.parent / ("najamjad-thief" if ROOT.name == "najamjad-cop" else "najamjad-cop")
    if not sibling.exists():
        pytest.skip("sibling repository not checked out")

    result = subprocess.run(
        ["uv", "run", "python", "scripts/sync_core.py", str(sibling)],
        cwd=ROOT, capture_output=True, text=True, timeout=300, check=False,
    )

    assert result.returncode == 0, f"core has drifted:\n{result.stdout[-2000:]}"


@pytest.mark.slow
def test_a_move_is_computed_well_inside_the_step_budget():
    """T-2123. The book allows 30 s per response; a move must not be the reason
    we approach it. Measured on the largest board we would ever negotiate."""
    import time

    from najamjad_agent.constants import Role
    from najamjad_agent.domain.movement import legal_moves
    from najamjad_agent.domain.params import GameParams
    from najamjad_agent.sdk.match_setup import build_brain
    from najamjad_agent.sdk.state_setup import build_state

    params = GameParams.from_config({
        "board_and_agents": {"grid_size": 15, "thief_start": [7, 7], "cop_start": [0, 0]},
        "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 40,
                                  "max_moves": 60, "survival_threshold": 60},
    })
    state = build_state(params, Role.COP, 1)
    brain = build_brain(Role.COP, state)
    facts = state.facts(legal_moves(state.board, state.own_position))

    brain.pick_move(facts)  # warm
    start = time.monotonic()
    for _ in range(10):
        brain.pick_move(facts)
        brain.pick_barrier(facts)
    elapsed = (time.monotonic() - start) / 10

    assert elapsed < 5.0, f"a move takes {elapsed:.2f}s on a 15x15 board"
