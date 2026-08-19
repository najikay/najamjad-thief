"""Agreeing terms before a mini-game, retrying the same one on failure.

Split from `match` to stay inside the file budget, and it reads better alone:
the rule it encodes is that a failed agreement must not consume a sub-game
number. We used to advance the counter while the opponent retried the same
game, so after two failures we numbered games 3 and 4 against their 5 and 6 —
and two reports describing one match with different `sub_game_number`s are
contradictory, which rules 33-35 can void both teams for.
"""

from __future__ import annotations

import time
from typing import Any

from ..shared.events import Emit

#: Extra attempts reserved for a peer whose gate is merely shut. A refusal
#: arrives in milliseconds, so these are cheap, and they are what actually
#: resynchronises two agents that started a few seconds apart.
#:
#: Ten of them covered forty seconds, which was the right size while the thing
#: being waited out was a cold start. Splitting our roles across two processes
#: (book Appendix ה rule 1) made it the wrong size: our cop process skips the
#: windows our thief plays and reaches mini-game 2 immediately, so against an
#: opponent that still runs *one* process it now waits out a whole mini-game
#: rather than a few seconds of skew. Forty seconds of budget against a
#: multi-minute game scored a technical outcome on a peer who was healthy,
#: playing, and doing nothing wrong.
#:
#: Ninety at four seconds is six minutes — longer than a 35-move mini-game and
#: still bounded, so a peer that is genuinely wedged is eventually resolved
#: rather than waited on forever. Nothing is spent unless the peer keeps
#: *answering* "busy", which is a live process telling us it is fine.
#: Priced against the OPPONENT's window, not our own clock. anrbj666 sequence
#: their windows — N+1 is not spawned until N settles — so waiting for a peer's
#: next window means waiting out a whole mini-game plus their process boot. They
#: measured it for us on 2026-08-19: a game can run ten minutes or more (their
#: g03 spent 604 seconds on the handshake alone) and each window costs another
#: 15-20 seconds to spawn. Six minutes was priced against our own cold start and
#: was simply the wrong quantity; a hundred attempts at ten seconds is sixteen
#: minutes, which outlasts their longest observed window with room to spare and
#: is still bounded, so a genuinely dead peer is resolved rather than waited on.
BUSY_RETRIES = 100
BUSY_BACKOFF_SECONDS = 10.0
#: Failures that mean "the peer is not listening *yet*", as opposed to "the peer
#: is broken". Under a sequential-window contract — anrbj666 confirmed theirs on
#: 2026-08-19: windows run 1..6 and N+1 is not spawned until N settles — a door
#: with nothing behind it is the ordinary state of the *next* window while the
#: current one is still being played. It is the busy case wearing a different
#: coat: a timeout or a 502 rather than a refusal, because there is no process
#: there to say "busy".
#:
#: It cost us a series. Our ordinary budget is priced in minutes and theirs in
#: whole mini-games, so we exhausted it against a peer who was healthy and had
#: simply not reached that window yet, then advanced past a window that never
#: played. Connection-class failures therefore draw on the generous budget.
NOT_READY_YET = ("TimeoutError", "ConnectError", "ConnectTimeout", "ReadTimeout",
                 "RemoteProtocolError", "HandshakeError")


def agree_on_terms(
    handshake: Any,
    sub_game: int,
    retries: int,
    emit: Emit,
    role: str = "",
    sleep: Any = None,
) -> bool:
    """Run the pre-game handshake, retrying the *same* sub-game on failure.

    Input: the injected handshake callable (None when unconfigured), which
        mini-game is being agreed, how many retries the config allows, the
        event sink, and the role we hold this mini-game.

    `role` is forwarded because the peer's handshake declares the endpoint
    for the role *they* are playing, and which of their addresses we should
    dial therefore depends on which of ours we hold. Optional so every
    existing caller and test keeps working.
    Output: True once terms are agreed; False when the attempts are exhausted,
        which the caller resolves as a technical outcome rather than a game.
    Setup: `network.handshake_retries` in the role config.

    Catches broadly because the handshake is an injected boundary — the domain
    must not import the negotiation layer to name its exception, and every
    failure here means the same thing: no agreed terms, nothing to play yet.
    Every attempt is announced; a silent retry hides the tunnel problem an
    operator needs to hear about before it happens mid-series.
    """
    sleep = sleep or time.sleep
    if handshake is None:
        return True
    ordinary = 0
    busy_seen = 0
    while True:
        try:
            _invoke(handshake, role, sub_game)
        except Exception as error:  # noqa: BLE001 - injected boundary, reported
            # A peer answering "busy, ask again at the boundary" is healthy and
            # mid-mini-game: our clocks drifted and they started first. That
            # deserves a short wait, **not** one of the ordinary attempts —
            # spending the real budget on it is how a few seconds of skew became
            # a lost series, because the budget ran out long before their
            # sub-game ended. So the two are counted separately.
            if type(error).__name__ in ("HandshakeBusyError", *NOT_READY_YET):
                busy_seen += 1
                spent = busy_seen > BUSY_RETRIES
                emit({
                    "event": "handshake.exhausted" if spent else "handshake.waiting_for_window",
                    "sub_game": sub_game,
                    "attempt": busy_seen,
                    "error": f"{type(error).__name__}: {error}",
                })
                if spent:
                    return False
                sleep(BUSY_BACKOFF_SECONDS)
                continue
            ordinary += 1
            spent = ordinary > retries
            emit({
                "event": "handshake.exhausted" if spent else "handshake.retry",
                "sub_game": sub_game,
                "attempt": ordinary,
                "error": f"{type(error).__name__}: {error}",
            })
            if spent:
                return False
        else:
            return True


def _invoke(handshake: Any, role: str, sub_game: int) -> Any:
    """Call the handshake with whichever of `role` and `sub_game` it accepts.

    The injected callable is a boundary and older ones take no arguments. A
    `TypeError` from the call itself would be indistinguishable from one raised
    *inside* the handshake, so capability is inspected rather than guessed at
    from an exception.

    Arguments are matched **by name** rather than by position. `sub_game` was
    added after `role`, and a positional call would have handed the sub-game
    number to any existing two-parameter callable that spelled its parameters
    differently — silently, and only visible in the declaration a peer refuses.
    """
    import inspect

    try:
        accepted = set(inspect.signature(handshake).parameters)
    except (TypeError, ValueError):
        return handshake()
    available = {"role": role, "sub_game": sub_game}
    kwargs = {name: value for name, value in available.items() if name in accepted}
    if kwargs:
        return handshake(**kwargs)
    # A callable that takes something we cannot name still gets the role, which
    # is the argument every pre-existing handshake took positionally.
    return handshake(role) if accepted else handshake()
