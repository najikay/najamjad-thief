"""The pre-game agreement exchange (T-2307).

The reference implementation — and therefore most of the class — sends its
signed terms to our `negotiate` tool and then **waits for ours in return**. If
it never arrives it prints `Opponent never sent its agreement` and exits before
a single move is played.

Our `match` verb used to go straight to `play_series()`. Against ourselves that
was invisible, because neither side asked; against the reference it failed every
time. This module is the missing half.

The exchange is deliberately symmetric: both peers send unconditionally and then
wait. There is no leader to elect and no ordering to agree, which means it works
regardless of who started first.
"""

from __future__ import annotations

from typing import Any

from ..net.match_gate import BUSY_REASON
from ..shared.events import Emit
from .contract import Contract, ContractError
from .terms import describe_mismatch


class HandshakeBusyError(Exception):
    """The peer is mid-mini-game and asked us to re-send at the boundary.

    Separate from `HandshakeError` because the right response is different: a
    healthy peer with a shut gate should be retried promptly, not treated as an
    unreachable opponent and waited out.
    """


class HandshakeError(Exception):
    """The agreement could not be reached; naming why, for a human."""


def refused_as_busy(answer: Any) -> bool:
    """Whether the peer answered "a mini-game is in progress, ask again".

    Read from the response body rather than an exception, because a conforming
    server never raises at a caller — `mcp_server._handle` returns
    `{"accepted": False, "errors": [...]}` and that is the whole signal.
    """
    if not isinstance(answer, dict) or answer.get("accepted") is not False:
        return False
    return any(BUSY_REASON in str(error) for error in answer.get("errors") or ())


def _busy_detail(answer: Any) -> str:
    """The peer's own sentence, for the log and the retry event."""
    errors = answer.get("errors") if isinstance(answer, dict) else None
    return str((errors or [BUSY_REASON])[0])


def exchange_agreement(
    terms: dict[str, Any],
    identity: dict[str, Any],
    send: Any,
    receive: Any,
    timeout: float = 60.0,
    emit: Emit | None = None,
    declarations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sign our terms, swap with the opponent, and verify they signed the same.

    Returns the peer's message on success. Raises `HandshakeError` with a
    human-usable reason otherwise — the two failures that actually happen are
    "they never answered" and "we disagree about term X", and those need very
    different responses from an operator.
    """
    announce = emit or (lambda _event: None)
    contract = Contract(terms, identity=identity, declarations=declarations)
    ours = contract.signed()

    announce({"event": "handshake.sending", "sha256": contract.sha256})
    answer = send(ours)
    if refused_as_busy(answer):
        # Their gate is shut because a mini-game is in progress: our clocks
        # drifted and they started before us. Retriable by design, and the
        # retry is what resynchronises us — but only if it happens *soon*.
        #
        # Waiting `timeout` here is what turned a few seconds of skew into a
        # lost series against Amjad: the refusal arrives immediately, over a
        # healthy connection, and we then sat out the full 60 s as though
        # nobody had answered, three attempts running, while they played
        # sub-game 1 and timed out waiting for turns we could not send.
        announce({"event": "handshake.busy", "detail": _busy_detail(answer)})
        raise HandshakeBusyError(_busy_detail(answer))

    peer = receive(timeout)
    if peer is None:
        raise HandshakeError(
            f"the opponent sent no agreement within {timeout:.0f}s — are they running, "
            "and does their config point at our URL?"
        )

    try:
        contract.verify_peer(peer)
    except ContractError as error:
        mismatch = describe_mismatch(terms, dict(peer.get("terms") or {}))
        announce({"event": "handshake.refused", "reason": str(error), "mismatch": mismatch})
        raise HandshakeError(
            f"the opponent signed different terms — {mismatch}. "
            "Both peers must hold a byte-identical agreement before play starts."
        ) from error

    announce({
        "event": "handshake.locked",
        "sha256": contract.sha256,
        "peer_identity": peer.get("identity", {}),
    })
    return peer
