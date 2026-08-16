"""What we emit must be as visible in our own logs as what we absorb.

`scent.absorbed` has recorded every inbound frame's size and peak since the day a
peer sending 29 cells and a peer sending none became indistinguishable to us. The
outbound half had no event at all, so "are we emitting on the same terms they
are?" was unanswerable from our own log — and the answer turned out to be no. We
transmit pre-decay at peak 0.9; imreeyal and vibecode transmit post-decay at 0.8,
which we learned by reading their source rather than by comparing two numbers we
could have been recording all along.

Driven through the real `MatchRunner`, because a logging line that is never
reached is the exact failure this repo keeps finding. The two-process harness
cannot serve as the proof — it writes into a `TemporaryDirectory` deleted when it
exits, so its events are gone before anyone can read them.
"""

from __future__ import annotations

from najamjad_agent.constants import Role
from tests.fakes.network import linked_pair
from tests.integration.test_match_series import build_runner, play_pair


def _played_events() -> list[dict]:
    captured: list[dict] = []
    left, right = linked_pair()
    cop_first = build_runner(left, "najamjad", "rival", Role.COP)
    thief_first = build_runner(right, "rival", "najamjad", Role.THIEF)
    cop_first._emit = captured.append  # noqa: SLF001
    play_pair(cop_first, thief_first)
    return captured


def test_a_played_series_records_what_we_emitted() -> None:
    """The regression: our own emission reached no log line whatsoever."""
    emitted = [e for e in _played_events() if e.get("event") == "scent.emitted"]

    assert emitted, "a whole series went out and our own emission was never logged"
    for event in emitted:
        assert set(event) >= {"step", "cells", "peak", "mode"}


def test_both_directions_are_logged_in_the_same_terms() -> None:
    """Comparable fields, or `scent_parity.py` is comparing two different things.

    The point of the outbound event is the *comparison*, so the two sides must
    carry the same keys. An inbound frame described by `cells`/`peak` and an
    outbound one described by anything else would make the parity report a
    reformatting of one side rather than a measurement of both.
    """
    events = _played_events()
    outbound = [e for e in events if e.get("event") == "scent.emitted"]
    inbound = [e for e in events if e.get("event") == "scent.absorbed"]

    assert outbound and inbound
    shared = {"step", "cells", "peak"}
    assert shared <= set(outbound[0]) and shared <= set(inbound[0])


def test_their_peak_cell_is_recorded_and_ours_never_is() -> None:
    """The asymmetry is a leak guard, not an oversight.

    Post-hoc is where opponent auditing happens: `verify_trail` settles honesty
    live from frames held in memory for one mini-game, while an archived event
    log has to answer the same question months later — and a peak *value* cannot,
    because it says a field had a centre and not where. The vibecode friendly
    left 68 frames whose honesty is now permanently unknowable for that reason.

    But the centre of our *own* freshest deposit is our own current cell, and the
    event stream is served to a dashboard that a practice run binds to `0.0.0.0`.
    Recording it there publishes the one thing commit-reveal exists to seal;
    `test_nothing_the_dashboard_shows_discloses_the_thiefs_position` caught it
    within a day. It costs the audit nothing, because our own emission is
    checkable against our own sealed records and theirs is not.
    """
    events = _played_events()
    inbound = [e for e in events if e.get("event") == "scent.absorbed"]
    outbound = [e for e in events if e.get("event") == "scent.emitted"]

    located = [e for e in inbound if e.get("peak_cell") and e["cells"]]
    assert located, "no absorbed frame carried the cell their field was centred on"
    for event in located:
        assert len(event["peak_cell"]) == 2
    assert all("peak_cell" not in event for event in outbound), (
        "our own field's peak cell is our own position — it must never be logged"
    )
