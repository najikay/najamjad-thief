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

from ..shared.events import Emit
from .contract import Contract, ContractError
from .terms import describe_mismatch


class HandshakeError(Exception):
    """The agreement could not be reached; naming why, for a human."""


def exchange_agreement(
    terms: dict[str, Any],
    identity: dict[str, Any],
    send: Any,
    receive: Any,
    timeout: float = 60.0,
    emit: Emit | None = None,
) -> dict[str, Any]:
    """Sign our terms, swap with the opponent, and verify they signed the same.

    Returns the peer's message on success. Raises `HandshakeError` with a
    human-usable reason otherwise — the two failures that actually happen are
    "they never answered" and "we disagree about term X", and those need very
    different responses from an operator.
    """
    announce = emit or (lambda _event: None)
    contract = Contract(terms, identity=identity)
    ours = contract.signed()

    announce({"event": "handshake.sending", "sha256": contract.sha256})
    send(ours)

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
