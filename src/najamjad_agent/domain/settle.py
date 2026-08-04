"""Letting a peer finish burying a mini-game before we offer them the next one.

When we abandon a mini-game mid-play the opponent does not know. They are still
waiting on a turn that is never coming, and they will sit there until their own
watchdog fires. Meanwhile we have already moved on and sent the handshake for
the *next* mini-game — into a peer that is still inside the previous one and has
no reason to answer it.

That is how one dead mini-game becomes two. Measured in
`tests/integration/test_series_survives_a_stall.py`, where a storm in game 2
also takes game 3.

**Scope of that measurement, stated honestly.** It was taken in the in-process
harness, whose deadlines are compressed to fractions of a second so the suite
stays fast. In production we retry the handshake three times at sixty seconds
against an agreed sixty-second watchdog, so a real series may well resynchronise
on its own. This is insurance, not a confirmed production fix, and it is written
that way: it costs a bounded wait on a path that has already lost a game.

**Why a wait and not a `quit` control message.** The control channel does have a
`quit` verb, and telling them directly would be faster. It would also be a verb
whose meaning is theirs to interpret, and a peer that reads `quit` as *abandon
the match* would cost us the five games we were trying to protect. We cannot
test that against their implementation before it matters. A wait needs no
cooperation and cannot be misread.
"""

from __future__ import annotations

from typing import Any

#: Cap on any single settle wait. The agreed watchdog is 60 s (Appendix F Table
#: 19), so beyond that the peer has certainly closed its game and more waiting
#: only burns the match clock.
MAX_SETTLE_SECONDS = 60.0


def settle_seconds(watchdog: float, abandoned: bool) -> float:
    """How long to pause before offering the peer the next mini-game.

    Input: the agreed watchdog in seconds, and whether the game just played was
    abandoned rather than finished.
    Output: seconds to wait — always 0.0 after a clean game.
    Setup: none.

    Zero on the healthy path is the whole design constraint. Five of six
    mini-games end cleanly, both peers close them together, and a delay there
    would add minutes to every series to insure against something that did not
    happen.
    """
    if not abandoned:
        return 0.0
    return max(0.0, min(MAX_SETTLE_SECONDS, float(watchdog)))


def settle(
    watchdog: float, abandoned: bool, sleep: Any, emit: Any = None, sub_game: int = 0
) -> float:
    """Pause for the peer to time out its side of an abandoned mini-game.

    `sleep` is injected so a test can assert the duration without spending it —
    a sixty-second sleep in the suite is a sixty-second sleep in CI too.

    Announced rather than silent: a match operator watching the dashboard needs
    to know the agent is deliberately waiting and not hung, which is exactly
    what a silent minute looks like.
    """
    seconds = settle_seconds(watchdog, abandoned)
    if seconds <= 0.0:
        return 0.0
    if emit is not None:
        emit({
            "event": "series.settling",
            "sub_game": sub_game,
            "seconds": round(seconds, 1),
            "reason": "letting the peer time out the game we abandoned",
        })
    sleep(seconds)
    return seconds
