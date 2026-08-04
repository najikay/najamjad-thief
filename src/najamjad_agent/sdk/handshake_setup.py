"""Building the pre-game agreement exchange.

Split from `bootstrap` when it crossed the size cap. It is a coherent unit on
its own: the handshake runs once per mini-game, swaps signed terms and
identities, and everything the artifacts later need — the opponent's group id,
their hardware spec, the locked contract hash — arrives through it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..shared.app_config import load_setup, setting
from ..shared.config import ConfigManager


def _handshake(manager: ConfigManager, bus, inboxes, transport, session: dict):
    """The pre-game agreement swap, as a callable the match runs first."""
    from ..negotiation.handshake import exchange_agreement
    from ..negotiation.identity import identity_from_config
    from ..negotiation.terms import terms_from_config

    def run(role: str = ""):
        """Sign, swap and verify the terms, then dial where they say they are.

        `role` is the one we hold this mini-game. It decides which of the
        opponent's declared endpoints is theirs to answer on, since they are
        always playing the other side.
        """
        from ..net.peer_endpoint import retarget

        terms = terms_from_config(manager)
        session["terms"] = terms
        session["identity"] = identity_from_config(manager)
        peer = exchange_agreement(
            terms=terms,
            identity=session["identity"],
            send=lambda payload: transport.send_negotiate(payload),
            # The inbox hands back a validated pydantic model; the handshake and
            # the contract both work in plain dicts, and `verify_peer` indexes
            # the message directly.
            receive=lambda timeout: _as_dict(inboxes.poll("negotiate", timeout=timeout)),
            timeout=float(manager.get("network.handshake_timeout_seconds", 60)),
            emit=bus.publish,
        )
        session["peer"] = peer
        # Adopt the address they just declared. Their handshake has always
        # carried it and we have always ignored it, dialling instead whatever
        # was typed into `network.opponent_url` before the match — which is
        # correct until the first opponent whose tunnel re-mints its hostname,
        # and then it is a series of sends into an address nobody is behind.
        # `identity` is declared `dict | str` and the schema's own docstring
        # says a bare group name is terser, not hostile. `dict("uoh-sqak")`
        # raises — and it would raise *after* the terms were agreed and
        # `handshake.locked` emitted, so `agree_on_terms` would retry an
        # exchange the peer considers finished, burn the full timeout three
        # times, and resolve every mini-game OPPONENT_QUIT. A whole series
        # lost to a peer doing nothing wrong.
        declared = peer.get("identity")
        if role:
            retarget(
                transport.client,
                declared if isinstance(declared, dict) else {},
                role,
                bus.publish,
            )
        return peer

    return run


def _inbound_ceiling(manager: ConfigManager) -> int:
    """How many messages a minute we will accept from the opponent.

    From `config/rate_limits.json`, never a literal at the call site: this is a
    tunable, and the last time it was hardcoded it silently forfeited a game.
    """
    from ..shared.rate_limits import for_service, load_rate_limits

    limits = load_rate_limits(Path(setting(load_setup(), "paths.rate_limits",
                                              "config/rate_limits.json")))
    return int(for_service(limits, "inbound_peer").requests_per_minute)


def _as_dict(message: Any) -> dict[str, Any] | None:
    """A polled inbox message as a plain dict, or None when nothing arrived.

    The inbox hands back a validated pydantic model; `Contract.verify_peer`
    and the handshake both index a plain mapping.
    """
    if message is None:
        return None
    if isinstance(message, BaseModel):
        return message.model_dump()
    if isinstance(message, dict):
        return message
    return None




