"""Per-step board reconstruction from the sealed state string.

The state string is inside the hash, so on a step that verifies the board it
describes is one nobody could have edited afterwards. That is why it, rather
than a convenience field beside it, is the source of truth here.
"""

from pathlib import Path

import pytest

from najamjad_agent.replay.rebuild import parse_state, step_view, summary_view, timeline
from najamjad_agent.replay.verifier import verify_log

REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "goldens" / "artifacts" / "log_segal-police-team-vs-segal-thief-team_g01.json"
)


def test_a_state_string_yields_grid_position_and_barriers():
    parsed = parse_state("grid=7x7;self=[4, 3];barriers=[[1, 1], [2, 5]]")

    assert parsed == {"size": 7, "position": [4, 3], "barriers": [[1, 1], [2, 5]]}


def test_an_empty_barrier_list_parses_as_empty():
    assert parse_state("grid=7x7;self=[0, 0];barriers=[]")["barriers"] == []


@pytest.mark.parametrize("state", [None, 42, "", "nonsense"])
def test_an_unparseable_state_yields_no_board_rather_than_an_error(state):
    assert parse_state(state).get("size") is None


def test_a_position_field_contradicting_the_sealed_state_is_flagged():
    """The state string is inside the hash; a stray field beside it is not."""
    verdict = type("V", (), {"step": 3, "verified": True, "reason": "", "commit": "a", "recomputed": "a"})()
    record = {"payload": {"state": "grid=7x7;self=[2, 2];barriers=[]", "position": [5, 5]}}

    view = step_view(record, verdict, index=3)

    assert "contradicts the sealed state" in view["warning"]
    assert view["position"] == [2, 2]


def test_an_agreeing_position_field_raises_no_warning():
    verdict = type("V", (), {"step": 1, "verified": True, "reason": "", "commit": "a", "recomputed": "a"})()
    record = {"payload": {"state": "grid=7x7;self=[2, 2];barriers=[]", "position": [2, 2]}}

    assert step_view(record, verdict, index=1)["warning"] == ""


@pytest.mark.goldens
def test_the_reference_log_rebuilds_a_board_for_every_playing_step():
    result = verify_log(REFERENCE)

    views = timeline(result)

    assert len(views) == 19
    assert views[0]["kind"] == "system_spec"
    assert views[0]["size"] == 0, "step zero carries no board"
    assert all(view["size"] == 7 for view in views[1:])
    assert all(view["position"] is not None for view in views[1:])


@pytest.mark.goldens
def test_the_reference_log_keeps_hint_and_provenance_per_step():
    views = timeline(verify_log(REFERENCE))

    assert views[1]["hint"] == "I keep moving through the streets."
    assert views[1]["move"] == "MOVE:S"
    assert views[1]["intent"] == "truth"
    assert views[1]["model"] == "stub"


@pytest.mark.goldens
def test_the_summary_carries_the_banner_and_the_logs_own_metadata():
    summary = summary_view(verify_log(REFERENCE))

    assert summary["banner"] == "Verified OK"
    assert summary["verified"] == summary["steps"] == 19
    assert summary["game_id"] == "segal-police-team-vs-segal-thief-team"
    assert (summary["role"], summary["winner_role"]) == ("thief", "police")


def test_a_step_that_failed_carries_both_hashes_so_the_claim_is_checkable():
    log = verify_log(
        {"records": [{"payload": {"step": 1}, "nonce": "ab", "commit": "not-the-right-hash"}]}
    )

    view = timeline(log)[0]

    assert view["verified"] is False
    assert view["commit"] == "not-the-right-hash"
    assert len(view["recomputed"]) == 64
