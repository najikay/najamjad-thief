"""A peer re-offering the window we are already in is not premature.

We start a window the moment *our* side agrees. The peer may not consider it
agreed for seconds afterwards, and everything they send to close that gap is a
negotiate naming the very window we are sitting in. Refusing those is how both
sides wait forever.

anrbj666, 2026-08-21, g04. Our police started the window at 12:25:49 on our own
agreement. Their thief then re-offered g04 **thirty-one times**; our gate
answered "a mini-game is in progress" to every one, so their side never reached
an agreed window and never sent an opener. Our police waited at `step: 0`, timed
out, and the stall took g05 and g06 with it. Counted from our own log: 34
negotiates parsed in that window, 3 accepted, and **zero turns**.

The refusal is right in general — it is what stopped ahk-yosi's peer running two
games over one inbox — so this narrows it rather than removing it: accepted only
while no turn has been exchanged, and only for the window already in play.
Idempotent by construction, since the terms are identical and our reply carries
our own agreement, which is exactly what the peer was missing.
"""

from __future__ import annotations

from types import SimpleNamespace

from najamjad_agent.net.match_gate import BUSY_REASON, MatchGate


def offer(sub_game: int | None) -> SimpleNamespace:
    return SimpleNamespace(sub_game_number=sub_game, extras={})


def test_a_reoffer_of_the_live_window_is_accepted_before_any_turn() -> None:
    """The g04 case, and the whole point of the change."""
    events: list[dict] = []
    gate = MatchGate(emit=events.append)
    gate.begin_sub_game(4)

    assert gate.refuse(offer(4), turns_seen=False) is None
    assert events[-1]["event"] == "handshake.reoffer_accepted"


def test_once_turns_are_flowing_it_is_refused_again() -> None:
    """Then a fresh negotiate really would restart a live game."""
    gate = MatchGate()
    gate.begin_sub_game(4)

    assert gate.refuse(offer(4), turns_seen=True) == BUSY_REASON


def test_a_different_window_is_still_refused() -> None:
    """A peer running ahead of us gets the retriable answer, as before."""
    gate = MatchGate()
    gate.begin_sub_game(4)

    assert gate.refuse(offer(5), turns_seen=False) == BUSY_REASON
    assert gate.refuse(offer(None), turns_seen=False) == BUSY_REASON


def test_the_number_may_arrive_as_an_undeclared_extra() -> None:
    """Peers whose schema we do not declare still carry it in extras."""
    gate = MatchGate()
    gate.begin_sub_game(2)
    message = SimpleNamespace(extras={"sub_game_number": 2})

    assert gate.refuse(message, turns_seen=False) is None


def test_an_open_gate_still_admits_anything() -> None:
    """Between mini-games nothing is premature; the series starts this way."""
    assert MatchGate().refuse(offer(3), turns_seen=False) is None


def test_a_junk_window_number_does_not_open_the_gate() -> None:
    """Unreadable is not a match, and must not become a bypass of the guard."""
    gate = MatchGate()
    gate.begin_sub_game(4)

    for junk in ("four", None, [], {}):
        assert gate.refuse(SimpleNamespace(sub_game_number=junk, extras={}),
                           turns_seen=False) == BUSY_REASON
