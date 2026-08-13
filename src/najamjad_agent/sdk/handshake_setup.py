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
    from ..negotiation.declarations import negotiate_declarations
    from ..negotiation.handshake import exchange_agreement
    from ..negotiation.identity import identity_from_config
    from ..negotiation.terms import terms_from_config

    def run(role: str = "", sub_game: int = 0):
        """Sign, swap and verify the terms, then dial where they say they are.

        `role` is the one we hold this mini-game. It decides which of the
        opponent's declared endpoints is theirs to answer on, since they are
        always playing the other side.

        `sub_game` is declared beside the terms so that two peers who disagree
        about which mini-game they are playing refuse at the handshake. One game
        carrying two sub-game indices is exactly the shape that makes two honest
        reports contradictory, and rules 33-35 void such a game for both teams.
        """
        from ..net.peer_endpoint import retarget

        terms = terms_from_config(manager)
        session["terms"] = terms
        session["identity"] = identity_from_config(manager)
        # Expect their role BEFORE the exchange, not after it. A peer whose
        # fresh process fires its opening turn the instant the handshake returns
        # lands in the gap between "agreed" and "bound", where the guard still
        # holds the PREVIOUS sub-game's role and refuses the one turn that
        # matters. See `_bind_expected_role`.
        _bind_expected_role(inboxes, manager, terms, session["identity"], role, bus.publish)
        peer = exchange_agreement(
            terms=terms,
            identity=session["identity"],
            declarations=negotiate_declarations(manager, terms, role, sub_game),
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
                # The **configured** pair, not what we advertise. Since
                # `served_endpoints` we publish only the address this process
                # serves — but a peer running our config still declares both
                # `4laboratory.com` hostnames, and the sibling is exactly the
                # one we must refuse to be sent to. Reading `ours` from the
                # identity would have quietly narrowed this guard at the moment
                # we narrowed the declaration.
                ours=dict(manager.get("game.mcp_servers", {}) or {}),
            )
        _bind_session(inboxes, session, declared, bus.publish, role)
        return peer

    return run


def _bind_expected_role(inboxes, manager, terms, identity, our_role: str, emit) -> None:
    """Bind the guard to their role before the agreement exchange, not after.

    The window this closes is milliseconds wide and cost three sub-games a
    night, three nights running. The guard pins `expected_sender` to the role
    the opponent holds *this* mini-game. We bound it after `exchange_agreement`
    returned — but a peer that runs each sub-game as a fresh process sends its
    opening turn the instant its own handshake completes, which is before our
    call has returned. The turn arrives while the guard still holds the previous
    sub-game's role, is refused as `sender 'thief' is not the negotiated
    opponent 'police'`, and we bind to the right role a beat later, having
    already thrown away the only turn that would have started the game.

    It bites exactly the sub-games where the opponent opens — for us the ones we
    play as police, since the thief opens — which is why it looks like a broken
    police role and is not one: our police captured 3 of 3 against the kit's
    sparring peer, whose opener is a fraction slower and lands after the bind.

    Nothing here waits on the peer. Our role for this mini-game gives theirs,
    and the token comes from the terms plus the two group ids, the opponent's
    read from the card — the same values `_bind_session` derives afterwards from
    their declared identity. So the later bind stays, as a correction rather
    than the first word, and this one is safe to be wrong: it can only ever
    expect the role the rules say they hold.
    """
    from ..negotiation.contract import contract_hash, derive_game_ids
    from ..net.peer_endpoint import OPPOSITE_ROLE

    theirs = OPPOSITE_ROLE.get(str(our_role).lower(), "")
    their_group = str(manager.get("network.opponent_group_id", "") or "").strip()
    our_group = str((identity or {}).get("group_id", ""))
    if not theirs or not their_group or their_group == "them":
        # Without a role we cannot name their sender, and without their group we
        # cannot derive the token. Staying unbound is the safe answer: an
        # unbound guard admits, which costs a guard we did not have anyway
        # rather than the turn that starts the game.
        emit({"event": "session.early_bind_skipped", "role": our_role, "group": their_group})
        return
    _, game_uid = derive_game_ids(dict(terms), our_group, their_group)
    inboxes.guard.bind(theirs, contract_hash(dict(terms)), game_uid)


def _bind_session(inboxes, session: dict, declared: Any, emit, our_role: str = "") -> None:
    """Admit only the peer we just signed with, for the rest of this game.

    Input: the inboxes owning the guard, the session dict (terms and our own
    identity), and whatever the peer declared as its identity.
    Output: none; the guard is bound as a side effect.
    Setup: call *after* a successful `exchange_agreement` and never before —
    binding on an unverified identity would let whoever spoke first lock us to
    themselves and shut the real opponent out.

    `SessionGuard` was written, documented and tested, and `bind` had no caller
    outside its own test file — the eighth finished-but-unreferenced component
    found in this repo. Until now `check()` returned early on `not self.bound`
    for every inbound message, so the identity half of that module has never
    run in a real match, while our MCP URL sits published in a public repo.

    **`sender` is a role, not a group — and getting that wrong cost every game.**
    The first version of this bound `expected_sender` to the opponent's group id
    and was defended in this docstring with "reference-implementation peers do
    not set the field". They do: `docs/research/simulator-repo-digest.md` records
    `"sender": "thief" | "police"` on the turn, audit and control messages, and
    our own `turn_egress` sends `state.role.value`. So the guard compared
    `"police"` against `"uoh-sqak"`, refused every inbound turn and every audit
    reveal from the first handshake onward, and would have lost the series
    without a single message reaching the game loop. A review caught it before a
    match did.

    What that means for the design: the wire has no per-message group id, so a
    group id is not something this guard can check. The **token** is the real
    identity proof — derived from a contract only the two of us hold, and
    unforgeable by a stranger. `expected_sender` is set to the role the opponent
    holds this mini-game, which is what their messages actually carry.

    **This cannot refuse an honest peer.** The role is the one we compute from
    ours, so a conforming opponent always matches; `check` compares only when
    the message carries a sender, and the token is enforced only when the peer
    sends one — the reference does not, and is admitted with an event.

    Both identifiers are derived, never transmitted: `contract_hash` over the
    terms we agreed and `derive_game_ids` over those terms plus the two group
    names. Both peers hold byte-identical terms, so both compute the same
    token without it ever crossing the wire.
    """
    from ..negotiation.contract import contract_hash, derive_game_ids

    identity = session.get("identity") or {}
    terms = session.get("terms") or {}
    their_group = str((declared or {}).get("group_id", "") if isinstance(declared, dict) else "")
    if not their_group:
        # A peer may legitimately send a bare group name, or nothing we can
        # read. Refusing to play over that would cost the match to protect it,
        # so we stay unbound and say so rather than binding to the empty string
        # — which would reject every message the opponent sends.
        emit({"event": "session.unbound", "reason": "peer declared no group id"})
        return
    our_group = str(identity.get("group_id", ""))
    _, game_uid = derive_game_ids(dict(terms), our_group, their_group)
    # Their role is the other one: roles alternate per mini-game and the
    # handshake runs per mini-game, so this is re-bound each time.
    from ..net.peer_endpoint import OPPOSITE_ROLE

    theirs = OPPOSITE_ROLE.get(str(our_role).lower(), "")
    if not theirs:
        # Without a role we cannot name what their `sender` should say, and
        # guessing would refuse an honest peer. The token still binds.
        emit({"event": "session.unbound", "reason": "our role is unknown"})
        return
    inboxes.guard.bind(theirs, contract_hash(dict(terms)), game_uid)
    emit({"event": "session.peer_group", "group_id": their_group})


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




