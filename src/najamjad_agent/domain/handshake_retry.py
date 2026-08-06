"""Agreeing terms before a mini-game, retrying the same one on failure.

Split from `match` to stay inside the file budget, and it reads better alone:
the rule it encodes is that a failed agreement must not consume a sub-game
number. We used to advance the counter while the opponent retried the same
game, so after two failures we numbered games 3 and 4 against their 5 and 6 —
and two reports describing one match with different `sub_game_number`s are
contradictory, which rules 33-35 can void both teams for.
"""

from __future__ import annotations

from typing import Any

from ..shared.events import Emit


def agree_on_terms(
    handshake: Any, sub_game: int, retries: int, emit: Emit, role: str = ""
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
    if handshake is None:
        return True
    for attempt in range(1 + retries):
        try:
            _invoke(handshake, role)
        except Exception as error:  # noqa: BLE001 - injected boundary, reported
            emit({
                "event": "handshake.retry" if attempt < retries else "handshake.exhausted",
                "sub_game": sub_game,
                "attempt": attempt + 1,
                "error": f"{type(error).__name__}: {error}",
            })
        else:
            return True
    return False


def _invoke(handshake: Any, role: str) -> Any:
    """Call the handshake, passing the role only if it accepts one.

    The injected callable is a boundary and older ones take no arguments. A
    `TypeError` from the call itself would be indistinguishable from one raised
    *inside* the handshake, so capability is inspected rather than guessed at
    from an exception.
    """
    import inspect

    try:
        takes_role = bool(inspect.signature(handshake).parameters)
    except (TypeError, ValueError):
        takes_role = False
    return handshake(role) if takes_role else handshake()
