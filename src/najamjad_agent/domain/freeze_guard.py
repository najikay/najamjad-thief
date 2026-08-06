"""Arming rule 7 freeze detection for one mini-game.

Split from `MatchRunner` at the size cap, and it earns its own file: this is
the only place in the project that answers "how do we tell a frozen agent from
a slow one", and that question has a long enough answer to be worth reading on
its own.

`net/watchdog.py` was written, documented and unit-tested, and nothing in
`src/` ever constructed it — the eighth finished-but-unreferenced component
found here. So the protection rule 7 requires has not existed at runtime for
the whole project. This module is its caller.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ..shared.events import Emit
from .game_state import GameState

#: How many agreed watchdogs of silence mean a freeze rather than a slow turn.
#: Three is not caution for its own sake. Even with the gatekeeper's deadline
#: in place a single send may spend its whole 45 s budget and then sit in the
#: final attempt's 30 s response timeout — Table 19 fixes that timeout, so the
#: overrun is legal and unavoidable — and one turn makes several sends. At a
#: threshold of one watchdog this fires on a slow but perfectly healthy turn.
FREEZE_MULTIPLE = 3


@contextmanager
def watching(
    watchdog_seconds: float, state: GameState, sub_game: int, emit: Emit
) -> Iterator[Callable[[], None] | None]:
    """Watch one mini-game for a freeze, yielding its heartbeat.

    Input: the agreed watchdog in seconds (zero disables), the live state, the
    mini-game number, and where to publish.
    Output: the `beat` the turn loop calls each half-turn, or None when
    disabled — `run_turn_loop` accepts either.
    Setup: runs a daemon thread for the duration of the block.

    A context manager rather than a start/stop pair because the thread must be
    joined however the game ends, and the ways it can end include an exception
    from the turn loop. Every `try/finally` a caller has to remember is one it
    can forget.

    **What it can and cannot do**, stated plainly because the difference is the
    whole design. It cannot interrupt a thread blocked in a socket read — no
    watchdog on a daemon thread can. What actually bounds our blocking is the
    gatekeeper's wall-clock deadline, and this is deliberately armed only now
    that the deadline exists: at the old ~645 s worst case a 60 s watchdog
    would have fired on healthy retrying and thrown away winnable games.

    What it does do is notice a genuine deadlock, persist the live state so the
    mini-game stays auditable, and say so in the event log.

    **Rescue is record, not kill.** Aborting the process would forfeit every
    remaining mini-game, and rule 35 scores a missing report as not having
    played — so a series that files six results beats one that files two and a
    stack trace. `Watchdog` takes a shutdown callback because other callers
    might want one; ours deliberately does nothing, since the only thing worth
    stopping is the turn loop and it is, by hypothesis, not answering.
    """
    if watchdog_seconds <= 0:
        yield None
        return
    from ..net.watchdog import Watchdog

    def persist() -> None:
        emit({"event": "watchdog.snapshot", "sub_game": sub_game, "state": state.snapshot()})

    guard = Watchdog(
        threshold_seconds=watchdog_seconds * FREEZE_MULTIPLE,
        persist_state=persist,
        controlled_shutdown=lambda: None,
        emit=emit,
    )
    guard.start()
    try:
        yield guard.beat
    finally:
        guard.stop()
