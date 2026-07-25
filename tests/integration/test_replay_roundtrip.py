"""A game we actually played, replayed through our own viewer.

The golden tests prove we can verify the lecturer's log. This proves the other
direction: that what our orchestrator seals during a real mini-game is something
the viewer can re-hash and reconstruct. Both halves are needed — a verifier that
only reads foreign logs, or an agent whose own logs do not replay, would each
fail submission in a different way.
"""

import json

import pytest
from fastapi.testclient import TestClient

from najamjad_agent.constants import Move, Role
from najamjad_agent.replay.app import create_replay_app
from najamjad_agent.replay.verifier import verify_log
from tests.integration.test_headless_game import LinkedTransport, _peer, _play


@pytest.fixture()
def played_log() -> dict:
    """Two peers play three turns; we take the cop's revealed records."""
    cop_link, thief_link = LinkedTransport(), LinkedTransport()
    cop_link.connect(thief_link)
    cop = _peer(Role.COP, [Move.SOUTH] * 6, cop_link)
    thief = _peer(Role.THIEF, [Move.EAST] * 6, thief_link)
    _play(cop, thief, turns=3)
    cop.state.ledger.open_audit()
    return {"records": cop.state.ledger.audit_payload()}


def test_our_own_sealed_game_replays_verified_ok(played_log):
    result = verify_log(played_log)

    assert result.banner == "Verified OK"
    assert len(result.steps) == 3
    assert result.failed_indices == []


def test_the_viewer_rebuilds_the_path_we_actually_walked(played_log):
    """The cop moved south three times, so the reconstruction must show that."""
    with TestClient(create_replay_app(played_log)) as viewer:
        steps = viewer.get("/api/replay/steps").json()["steps"]

    rows = [view["position"][0] for view in steps]

    assert rows == sorted(rows), "a southward walk must have non-decreasing rows"
    assert all(view["size"] == 7 for view in steps)
    assert all(view["verified"] for view in steps)


def test_editing_one_move_in_our_own_log_is_caught_at_that_step(played_log):
    """Rule 19 applies to us exactly as it does to an opponent."""
    tampered = json.loads(json.dumps(played_log))
    tampered["records"][1]["payload"]["move"] = "MOVE:N"

    result = verify_log(tampered)

    assert result.banner == "TAMPERED"
    assert result.void is True
    assert result.failed_indices == [1]


def test_a_log_written_to_disk_replays_the_same_as_one_in_memory(played_log, tmp_path):
    path = tmp_path / "log_najamjad_g01.json"
    path.write_text(json.dumps(played_log), encoding="utf-8")

    from_disk, from_memory = verify_log(path), verify_log(played_log)

    assert from_disk.report == from_memory.report
    assert [step.commit for step in from_disk.steps] == [
        step.commit for step in from_memory.steps
    ]
