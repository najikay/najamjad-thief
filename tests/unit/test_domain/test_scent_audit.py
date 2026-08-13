"""Their transmitted trail, checked against the positions they later reveal.

Scent is the channel the book calls unfakeable, but that is a property of an
honest implementation and not of the wire: nothing stopped a peer broadcasting a
field centred where it has never been, and we absorbed every grid silently.

imreeyal re-simulated all 105 of our grids against our revealed positions and
reported them consistent to the last cell. We could not return the favour.

The check is the **argmax**, not a re-simulation: the centre of the freshest
deposit is the unique maximum of an honest field, so the peak names where the
emitter stood on the step it sent. That is independent of which snapshot a peer
transmits — teams in this league legitimately differ between the pre-decay 0.9
form and the post-decay 0.8 one, and a re-simulation would have to know which.
"""

from __future__ import annotations

from najamjad_agent.domain.scent_audit import FrameLog, verify_trail


def _records(*pairs: tuple[int, tuple[int, int]]) -> list[dict]:
    """Their revealed records, in the audit's `{payload: {...}}` envelope."""
    return [{"payload": {"step": step, "position": list(cell)}} for step, cell in pairs]


def _trail(centre: tuple[int, int], peak: float = 0.8) -> dict[str, float]:
    """A grid whose unique maximum is `centre`, with a decayed tail around it."""
    row, col = centre
    grid = {f"{row},{col}": peak}
    for delta_r, delta_c in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        grid[f"{row + delta_r},{col + delta_c}"] = round(peak - 0.3, 3)
    return grid


def test_an_honest_trail_agrees_on_every_step() -> None:
    log = FrameLog()
    for step, cell in ((1, (3, 3)), (2, (3, 4)), (3, (4, 4))):
        log.record(step, _trail(cell))

    report = verify_trail(log, _records((1, (3, 3)), (2, (3, 4)), (3, (4, 4))))

    assert report.clean
    assert (report.checked, report.agreed) == (3, 3)
    assert report.as_event()["event"] == "scent.trail_verified"


def test_a_decoy_trail_is_caught_and_named() -> None:
    """The case this exists for: a field centred where they never stood."""
    log = FrameLog()
    log.record(1, _trail((3, 3)))
    log.record(2, _trail((0, 0)))          # they claim the corner
    log.record(3, _trail((4, 4)))

    report = verify_trail(log, _records((1, (3, 3)), (2, (3, 4)), (3, (4, 4))))

    assert not report.clean
    assert (report.checked, report.agreed) == (3, 2)
    step, peaks, revealed = report.mismatches[0]
    assert (step, revealed) == (2, (3, 4))
    assert peaks == ((0, 0),), "the report names the cell they claimed"
    assert report.as_event()["event"] == "scent.trail_mismatch"


def test_the_verdict_is_independent_of_which_snapshot_they_send() -> None:
    """0.9 pre-decay and 0.8 post-decay must both verify. Teams differ."""
    for peak in (0.9, 0.8):
        log = FrameLog()
        log.record(1, _trail((2, 5), peak=peak))

        assert verify_trail(log, _records((1, (2, 5)))).clean, f"peak {peak} failed"


def test_a_tie_is_not_a_lie() -> None:
    """A peer that stayed put re-deposits on its own cell; rounding can level a
    neighbour with it. Agreement is "the revealed cell is among the peaks"."""
    log = FrameLog()
    log.record(1, {"3,3": 0.8, "3,4": 0.8})

    assert verify_trail(log, _records((1, (3, 4)))).clean


def test_a_silent_peer_is_unverifiable_rather_than_guilty() -> None:
    """Sending no scent is legal. It must never read as a failed check."""
    log = FrameLog()
    log.record(1, {})

    report = verify_trail(log, _records((1, (3, 3)), (2, (3, 4))))

    assert report.clean, "silence is not a mismatch"
    assert (report.checked, report.unverifiable) == (0, 2)
    assert report.as_event()["event"] == "scent.trail_verified"


def test_a_malformed_grid_never_raises() -> None:
    """Everything here arrives from a competitor; a broken reveal is evidence
    about them and must not take our own settlement down with it."""
    log = FrameLog()
    log.record(1, {"not-a-cell": 0.9, "3,3": "high", "4,4": 0.8})

    report = verify_trail(log, _records((1, (4, 4))))

    assert report.clean, "the one parsable numeric cell is the peak"


def test_a_malformed_reveal_is_skipped_rather_than_fatal() -> None:
    log = FrameLog()
    log.record(1, _trail((3, 3)))
    bad = [{"payload": {"step": 1, "position": "somewhere"}},
           {"payload": {"step": "x", "position": [3, 3]}}]

    assert verify_trail(log, bad).checked == 0


def test_the_event_bounds_a_flood_of_mismatches() -> None:
    """A peer whose every frame disagrees must not write a 35-entry structure
    into a line meant to be read at a glance."""
    log = FrameLog()
    revealed = []
    for step in range(1, 13):
        log.record(step, _trail((0, 0)))
        revealed.append((step, (5, 5)))

    event = verify_trail(log, _records(*revealed)).as_event()

    assert len(event["mismatches"]) == 5
    assert event["checked"] == 12 and event["agreed"] == 0


def test_the_log_forgets_between_mini_games() -> None:
    """Frames are per mini-game; carrying them over would check one game's
    grids against another game's positions."""
    log = FrameLog()
    log.record(1, _trail((3, 3)))
    log.clear()

    assert verify_trail(log, _records((1, (3, 3)))).checked == 0
