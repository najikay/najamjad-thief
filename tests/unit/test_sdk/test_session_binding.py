"""The handshake must actually bind the guard — the eighth dead component.

`SessionGuard` has been written, documented and unit-tested since early on, and
`bind` had no caller anywhere outside its own test file. `check()` therefore
returned early on `not self.bound` for every message a real opponent ever sent,
so the identity half of that module has never run in a match while our MCP URL
sits published in a public repository.

These tests assert the wiring, not the guard's own logic, because the wiring is
what was missing. `tests/unit/test_net/test_session_guard.py` still owns the
question of what a bound guard does.
"""

from typing import Any

from najamjad_agent.negotiation.contract import contract_hash, derive_game_ids
from najamjad_agent.net.session_guard import session_token
from najamjad_agent.sdk.handshake_setup import _bind_session

TERMS: dict[str, Any] = {"grid_size": 7, "max_moves": 35}
OURS = {"group_id": "najamjad", "group_name": "NajAmjad"}


class Inboxes:
    """Just enough of the real thing to see whether `bind` was reached."""

    def __init__(self) -> None:
        from najamjad_agent.net.session_guard import SessionGuard

        self.guard = SessionGuard()


def _session() -> dict[str, Any]:
    return {"terms": dict(TERMS), "identity": dict(OURS)}


def test_a_completed_handshake_locks_us_to_that_opponent() -> None:
    """The whole point: after signing, a stranger can no longer move for them."""
    inboxes = Inboxes()

    _bind_session(inboxes, _session(), {"group_id": "uoh-sqak"}, lambda _event: None)

    assert inboxes.guard.bound
    assert inboxes.guard.expected_sender == "uoh-sqak"


def test_the_token_is_derived_from_the_signed_terms() -> None:
    """Both peers compute it from identical terms; it never crosses the wire."""
    inboxes = Inboxes()

    _bind_session(inboxes, _session(), {"group_id": "uoh-sqak"}, lambda _event: None)

    _, game_uid = derive_game_ids(dict(TERMS), "najamjad", "uoh-sqak")
    assert inboxes.guard.expected_token == session_token(contract_hash(dict(TERMS)), game_uid)


def test_both_peers_derive_the_same_token_from_either_side() -> None:
    """`derive_game_ids` sorts the pair, so neither side's order changes it.

    If it did not, each peer would compute a different token from the same
    contract and every authenticated message would be refused as forged.
    """
    ours = derive_game_ids(dict(TERMS), "najamjad", "uoh-sqak")
    theirs = derive_game_ids(dict(TERMS), "uoh-sqak", "najamjad")

    assert ours == theirs


def test_a_peer_that_declares_no_group_leaves_us_unbound() -> None:
    """Refusing to play over this would cost the match to protect it.

    The schema allows a bare group name instead of an identity object, and its
    own docstring calls that terser rather than hostile. Binding to the empty
    string would then reject every message the opponent sent — losing a series
    to our own defence, which is how the inbound rate limit once cost a game.
    """
    events: list[dict] = []
    inboxes = Inboxes()

    for declared in ({}, None, "uoh-sqak", {"group_name": "no id here"}):
        _bind_session(inboxes, _session(), declared, events.append)

    assert not inboxes.guard.bound
    assert [event["event"] for event in events] == ["session.unbound"] * 4


def test_binding_cannot_refuse_a_peer_that_omits_the_sender() -> None:
    """The safety property that makes this landable days before a match.

    The reference implementation sets neither `sender` nor `session_token`, and
    a guard that demanded them would turn a conforming opponent into a forfeit.
    Enforcement is deliberately conditional on the field being present.
    """

    class Silent:
        sender = ""
        session_token = ""

    inboxes = Inboxes()
    _bind_session(inboxes, _session(), {"group_id": "uoh-sqak"}, lambda _event: None)

    assert inboxes.guard.check(Silent()) is None


def test_a_stranger_is_refused_once_we_are_bound() -> None:
    """What the binding buys: nobody else may move in our match."""

    class Interloper:
        sender = "someone-else"
        session_token = ""

    inboxes = Inboxes()
    _bind_session(inboxes, _session(), {"group_id": "uoh-sqak"}, lambda _event: None)

    refusal = inboxes.guard.check(Interloper())

    assert refusal is not None
    assert "someone-else" in refusal


def test_the_handshake_itself_reaches_the_binding() -> None:
    """Prove the *seam*, not just the helper — the bug here was a missing call.

    Every test above could pass while `run()` never invoked `_bind_session`,
    which is precisely the shape of the defect being fixed: `SessionGuard.bind`
    was correct, tested, and called by nothing. No integration test exercises
    the real handshake, so this drives `_handshake(...)`'s returned callable
    end to end against a peer that signs our terms, and asserts the guard comes
    out bound.
    """
    from najamjad_agent.negotiation.contract import Contract
    from najamjad_agent.negotiation.terms import terms_from_config
    from najamjad_agent.sdk.handshake_setup import _handshake
    from najamjad_agent.shared.config import ConfigManager

    manager = ConfigManager({
        "game": {"group_id": "najamjad", "group_name": "NajAmjad"},
        "network": {"handshake_timeout_seconds": 5},
    })
    inboxes = Inboxes()
    published: list[dict] = []

    class Bus:
        publish = staticmethod(published.append)

    class Transport:
        client = None

        @staticmethod
        def send_negotiate(_payload: dict) -> None:
            """The peer is simulated by `receive` below; nothing leaves here."""

    # Their side of the agreement: byte-identical terms, their own signature.
    peer_message = Contract(terms_from_config(manager)).signed()
    peer_message["identity"] = {"group_id": "uoh-sqak", "group_name": "UoH SQAK"}

    session: dict[str, Any] = {}
    inboxes.poll = lambda _kind, timeout: peer_message  # noqa: ARG005
    run = _handshake(manager, Bus(), inboxes, Transport(), session)
    run()

    assert inboxes.guard.bound, "a completed handshake left the guard unbound"
    assert inboxes.guard.expected_sender == "uoh-sqak"
