"""App settings and per-opponent folders (T-0309, T-0318, T-0319).

Both existed as literals before: `manager.get("ui.port", 8000)` looked like a
config lookup and was a hardcoded default, because no config file ever declared
`[ui]`. The guidelines put hardcoded tunables at threshold zero, and a lookup
whose default is the only value it ever returns is the hardest kind to notice.

The workspace helper is mostly about one thing: the opponent's group id arrives
from the wire, in a field they control, and it is about to become a path.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.shared.app_config import DEFAULT_PATH, load_setup, setting
from najamjad_agent.shared.workspace import (
    FALLBACK,
    artifact_dir,
    known_opponents,
    match_dir,
    safe_name,
)

SETUP = Path("config/setup.json")


# ------------------------------------------------------------------- settings


def test_the_shipped_settings_file_is_versioned():
    """Every shipped config carries a version (guidelines §7.2)."""
    assert json.loads(SETUP.read_text(encoding="utf-8"))["version"] == "1.00"


def test_the_values_the_code_reads_are_all_declared():
    """A key the code asks for and the file does not declare is a literal in
    disguise — the default becomes the only value it ever returns."""
    setup = load_setup(SETUP)

    for dotted in ("ui.port", "paths.artifacts", "paths.rate_limits",
                   "paths.workspace", "paths.events", "paths.matches"):
        assert setting(setup, dotted, None) is not None, f"{dotted} is not declared"


def test_a_missing_settings_file_degrades_rather_than_raising(tmp_path):
    """A match must not be lost to an absent app-settings file."""
    assert load_setup(tmp_path / "absent.json") == {}
    assert setting({}, "ui.port", 8000) == 8000


def test_unparseable_settings_degrade_the_same_way(tmp_path):
    broken = tmp_path / "setup.json"
    broken.write_text("{not json", encoding="utf-8")

    assert load_setup(broken) == {}


def test_documentation_keys_can_never_shadow_a_setting():
    """The file is written to be read by a person; the notes are not data."""
    assert setting(load_setup(SETUP), "ui._note", "unreachable") == "unreachable"


def test_the_dashboard_binds_to_loopback():
    """It shows our belief and our sealed state — exposing it would hand an
    opponent everything commit-reveal exists to hide (rules 8-9)."""
    assert setting(load_setup(SETUP), "ui.host", "") == "127.0.0.1"


def test_the_default_path_is_the_shipped_file():
    assert Path("config/setup.json") == DEFAULT_PATH


# ------------------------------------------------------------------ workspace


@pytest.mark.parametrize(
    "given,expected",
    [
        ("Segal-Police-Team", "segal-police-team"),
        ("../../etc/passwd", "etc-passwd"),
        ("team/../..", "team"),
        ("  spaced name  ", "spaced-name"),
        ("", FALLBACK),
        ("...", FALLBACK),
    ],
)
def test_an_opponent_name_is_made_safe_before_it_becomes_a_path(given, expected):
    """They choose this string and send it to us."""
    assert safe_name(given) == expected


def test_a_very_long_name_is_truncated_rather_than_refused():
    """A hostile peer should not be able to make us fail on a filename."""
    assert len(safe_name("x" * 500)) <= 64


def test_each_opponent_gets_its_own_folder(tmp_path):
    first = match_dir("team-a", tmp_path)
    second = match_dir("team-b", tmp_path)

    assert first != second
    assert first.is_dir() and second.is_dir()


def test_the_same_opponent_resolves_to_the_same_folder_twice(tmp_path):
    """Two matches against one team belong together."""
    assert match_dir("Team A", tmp_path) == match_dir("team-a", tmp_path)


def test_artifacts_live_under_the_match_they_belong_to(tmp_path):
    """Which files belong to which game must not be a question about
    timestamps."""
    directory = artifact_dir("rival", tmp_path)

    assert directory.parent == match_dir("rival", tmp_path)
    assert directory.is_dir()


def test_known_opponents_lists_played_matches_only(tmp_path):
    match_dir("beta", tmp_path)
    match_dir("alpha", tmp_path)
    (tmp_path / "_template").mkdir(exist_ok=True)
    (tmp_path / ".hidden").mkdir(exist_ok=True)

    assert known_opponents(tmp_path) == ["alpha", "beta"]


def test_no_matches_folder_is_an_empty_list_not_an_error(tmp_path):
    assert known_opponents(tmp_path / "nothing-here") == []
