"""The match browser (T-1819 support, league tracking T-2320).

Reads back what we actually filed, so the operator sees the same account the
lecturer received rather than a second one assembled from memory.

Two properties are load-bearing. A match found in both the live workspace and
its archive must appear **once**, or the standings double-count. And "nobody
audited this" must stay distinct from "this failed its audit", because
collapsing them turns a timeout into an accusation.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.sdk.match_history import match_history, standings, summarise

OURS = "najamjad"


def result(game_id: str, uid: str, ours: int = 30, theirs: int = 10,
           tampered: bool = False, confirmed: bool = True) -> dict:
    """A result artifact of the shape we file."""
    return {
        "game_id": game_id,
        "game_uid": uid,
        "groups": [OURS, "rival"],
        "num_sub_games": 2,
        "sub_games": [
            {"sub_game_number": n, "result": "capture", "winner_group": OURS,
             "score": {OURS: 20, "rival": 5}, "roles": {OURS: "police", "rival": "thief"},
             "audit": {"log_verified": not tampered, "tampered": tampered}}
            for n in (1, 2)
        ],
        "final_result": {"total_score": {OURS: ours, "rival": theirs},
                         "winner_group": OURS if ours > theirs else "rival",
                         "series_tie": ours == theirs},
        "mutual_agreement": {"confirmed": confirmed},
    }


def write(root: Path, name: str, payload: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"result_{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_filed_match_appears_in_the_history(tmp_path):
    write(tmp_path, "a-vs-b", result("a-vs-b", "uid-1"))

    history = match_history(tmp_path)

    assert len(history) == 1
    assert history[0]["total_score"] == {OURS: 30, "rival": 10}


def test_the_same_match_found_in_two_places_is_listed_once(tmp_path):
    """Artifacts live in the live workspace during a match and in the archive
    afterwards; the standings must not count it twice."""
    payload = result("a-vs-b", "uid-1")
    write(tmp_path / "workspace", "a-vs-b", payload)
    write(tmp_path / "matches/rival", "a-vs-b", payload)

    history = match_history(tmp_path / "workspace", tmp_path / "matches")

    assert len(history) == 1


def test_an_unreadable_artifact_is_skipped_not_fatal(tmp_path):
    (tmp_path / "result_broken.json").write_text("{not json", encoding="utf-8")
    write(tmp_path, "good", result("good", "uid-2"))

    assert len(match_history(tmp_path)) == 1


def test_no_artifacts_anywhere_is_an_empty_list(tmp_path):
    assert match_history(tmp_path / "nothing") == []


def test_a_clean_audit_and_a_failed_one_are_counted_separately(tmp_path):
    """A game nobody audited is not a game that failed its audit."""
    clean = summarise(result("a", "u1"), Path("result_a.json"))
    dirty = summarise(result("b", "u2", tampered=True), Path("result_b.json"))

    assert (clean["verified"], clean["tampered"]) == (2, 0)
    assert (dirty["verified"], dirty["tampered"]) == (0, 2)


def test_the_summary_never_carries_revealed_records(tmp_path):
    """Records and their nonces belong to the replay viewer, from a file."""
    payload = result("a-vs-b", "uid-1")
    payload["sub_games"][0]["records"] = [{"nonce": "secret", "payload": {}}]
    write(tmp_path, "a-vs-b", payload)

    row = match_history(tmp_path)[0]

    assert "records" not in json.dumps(row)
    assert "nonce" not in json.dumps(row)


def test_the_artifacts_beside_the_result_are_listed(tmp_path):
    """So the operator can find the four files without a shell."""
    write(tmp_path, "a-vs-b", result("a-vs-b", "uid-1"))
    (tmp_path / "declaration_a-vs-b.json").write_text("{}", encoding="utf-8")

    assert "declaration_a-vs-b.json" in match_history(tmp_path)[0]["artifacts"]


# ------------------------------------------------------------------ standings


def test_standings_count_matches_and_distinct_opponents(tmp_path):
    """The league rewards diversity: a fifth match against one team is worth
    less than a first against a new one."""
    history = [
        summarise(result("a-vs-rival", "u1"), Path("x.json")),
        summarise(result("a-vs-rival-2", "u2"), Path("x.json")),
    ]

    table = standings(history, OURS)

    assert table["matches"] == 2
    assert table["distinct_opponents"] == 1
    assert table["points"] == 60


def test_standings_surface_anything_unreported(tmp_path):
    """Rule 35 punishes not reporting as heavily as reporting falsely, so an
    unsent report has to be visible rather than merely absent."""
    history = [summarise(result("a", "u1", confirmed=False), Path("x.json"))]

    assert standings(history, OURS)["unreported"] == ["a"]


def test_standings_surface_a_tampered_verdict(tmp_path):
    history = [summarise(result("a", "u1", tampered=True), Path("x.json"))]

    assert standings(history, OURS)["tampered"] == ["a"]


@pytest.mark.parametrize("ours,theirs,expected", [(30, 10, 1), (10, 30, 0), (20, 20, 0)])
def test_wins_are_counted_from_the_filed_result(ours, theirs, expected):
    history = [summarise(result("a", "u1", ours=ours, theirs=theirs), Path("x.json"))]

    assert standings(history, OURS)["won"] == expected
