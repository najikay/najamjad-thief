"""The counted-match declaration, end to end — rules 37-38.

Each team declares at match start how many counted matches it has already
played; the diversity weighting is computed from the two declarations, and a
false one found at project review **disqualifies the declaring team**.

`CountedGames` was written, tested and never called by anything, so the figure
was declared nowhere at all. These tests are about the wiring rather than the
class: the fifth finished-but-unreferenced component in this repo, after
`attach_game`, `reconcile`, `record_message` and `record_report`.
"""

from pathlib import Path

import pytest

from najamjad_agent.negotiation.counted_games import CountedGames, tracker_for
from najamjad_agent.negotiation.identity import identity_from_config
from najamjad_agent.reporting.result_blocks import declaration_group


class Manager:
    """Config stand-in whose `paths.counted_games` we can point at a tmp file."""

    def __init__(self, path: Path) -> None:
        self._values = {"paths.counted_games": str(path), "game.group_id": "najamjad"}

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    return tmp_path / "counted_games.json"


def test_the_handshake_declares_the_count(store: Path) -> None:
    """The wiring that did not exist: the figure must reach the opponent."""
    identity = identity_from_config(Manager(store))

    assert identity["counted_matches_played"] == 0
    assert identity["counted_matches_remaining"] == 10


def test_the_declared_count_comes_from_the_tracker_not_a_setting(store: Path) -> None:
    """It must be impossible to type this number, which is why it is derived.

    A hand-maintained counter across ten matches under time pressure is how an
    honest team declares a wrong one.
    """
    tracker = CountedGames.load(store)
    tracker.record("peer-one", game_uid="g1", timestamp="2026-08-03T00:00:00Z")
    tracker.record("peer-two", game_uid="g2", timestamp="2026-08-03T01:00:00Z")

    identity = identity_from_config(Manager(store))

    assert identity["counted_matches_played"] == 2
    assert identity["opponents_already_counted"] == ["peer-one", "peer-two"]


def test_the_count_survives_a_restart(store: Path) -> None:
    """A lost count is a false declaration next time, so it persists at once."""
    CountedGames.load(store).record("peer-one", game_uid="g1", timestamp="t")

    assert tracker_for(Manager(store)).count == 1


def test_the_declaration_reaches_the_result_artifact(store: Path) -> None:
    """The lecturer reconciles reports; the figure has to be in the one we send."""
    tracker = CountedGames.load(store)
    tracker.record("peer-one", game_uid="g1", timestamp="t")

    block = declaration_group(identity_from_config(Manager(store)))

    assert block["counted_matches_played"] == 1


def test_a_second_match_against_one_opponent_is_refused(store: Path) -> None:
    """Rule 52 seals a pairing once counted; a repeat scores nothing."""
    tracker = CountedGames.load(store)
    tracker.record("peer-one", game_uid="g1", timestamp="t")

    with pytest.raises(Exception, match="already been counted"):
        tracker.record("peer-one", game_uid="g2", timestamp="t")

    assert tracker.count == 1, "a refused match must not inflate the declaration"


def test_the_cap_of_ten_is_enforced(store: Path) -> None:
    tracker = CountedGames.load(store)
    for index in range(10):
        tracker.record(f"team-{index}", game_uid=f"g{index}", timestamp="t")

    assert tracker.remaining == 0
    with pytest.raises(Exception, match="cap of 10"):
        tracker.record("one-too-many", game_uid="g", timestamp="t")


def test_the_minimum_to_pass_is_reported_honestly(store: Path) -> None:
    """Two matches against *different* teams, or no passing grade (rule 31)."""
    tracker = CountedGames.load(store)

    assert not tracker.passes_minimum
    tracker.record("a", game_uid="1", timestamp="t")
    assert not tracker.passes_minimum
    tracker.record("b", game_uid="2", timestamp="t")
    assert tracker.passes_minimum


class Bus:
    """Event bus stand-in that keeps what was published."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(event)


def kinds(bus: Bus) -> list[str]:
    return [event["event"] for event in bus.events]


def test_a_counted_match_is_recorded_once_it_has_been_filed(store: Path, monkeypatch) -> None:
    """Recorded *after* filing: "matches played" means a report exists.

    Recording earlier would make the next declaration overstate us, which is
    the direction rules 37-38 disqualify for.
    """
    from najamjad_agent.sdk import match_filing
    from najamjad_agent.shared import practice

    monkeypatch.setattr(practice, "current", lambda: practice.PracticeMode(enabled=False))
    bus = Bus()
    match_filing._record_counted(Manager(store), bus, "peer-one", "uid-1")

    assert "counted.recorded" in kinds(bus)
    assert tracker_for(Manager(store)).count == 1


def test_a_practice_run_never_touches_the_count(store: Path, monkeypatch) -> None:
    """An uncounted game must not inflate a binding declaration.

    Gated on the same switch that redirects the mail, so the two cannot
    disagree about what kind of run this was.
    """
    from najamjad_agent.sdk import match_filing
    from najamjad_agent.shared import practice

    monkeypatch.setattr(
        practice, "current", lambda: practice.PracticeMode(enabled=True, redirect_to="me@example.com")
    )
    bus = Bus()
    match_filing._record_counted(Manager(store), bus, "peer-one", "uid-1")

    assert "counted.skipped" in kinds(bus)
    assert tracker_for(Manager(store)).count == 0


def test_replaying_the_same_opponent_does_not_double_count(store: Path, monkeypatch) -> None:
    from najamjad_agent.sdk import match_filing
    from najamjad_agent.shared import practice

    monkeypatch.setattr(practice, "current", lambda: practice.PracticeMode(enabled=False))
    bus = Bus()
    match_filing._record_counted(Manager(store), bus, "peer-one", "uid-1")
    match_filing._record_counted(Manager(store), bus, "peer-one", "uid-2")

    assert "counted.duplicate" in kinds(bus)
    assert tracker_for(Manager(store)).count == 1


def test_a_failing_tracker_never_undoes_a_played_match(tmp_path: Path, monkeypatch) -> None:
    """The match happened. A bookkeeping failure must be loud, not fatal.

    An unwritable location, made so by putting a *file* where the tracker needs
    a directory — `save()` creates parents, so a merely deep path succeeds and
    my first version of this test proved nothing.

    The recovery is to add the entry by hand before the next handshake, which
    is why this is evented rather than swallowed: a silent miss here becomes an
    understated declaration, and rules 37-38 do not care which direction the
    error went.
    """
    from najamjad_agent.sdk import match_filing
    from najamjad_agent.shared import practice

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(practice, "current", lambda: practice.PracticeMode(enabled=False))
    bus = Bus()

    match_filing._record_counted(Manager(blocker / "counted.json"), bus, "x", "uid")

    assert kinds(bus) == ["counted.record_failed"]
    assert bus.events[0]["opponent"] == "x"
