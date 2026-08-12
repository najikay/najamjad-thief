"""Their opening turn must not land in the gap between agreed and bound.

The thief opens every sub-game, so in the sub-games we play as police the
opponent drives the first message. A peer running each sub-game as a fresh
process sends that opener the instant its own handshake completes — before our
`exchange_agreement` has returned. We bound the guard *after* that call, so the
turn arrived while `expected_sender` still held the previous sub-game's role:

    session.rejected     reason=sender, sender=thief
    inbox.unauthorised   "sender 'thief' is not the negotiated opponent 'police'"
    session.bound        opponent=thief        <- one beat too late

Three sub-games a night, three nights, always the even ones. It reads as a
broken police role and is not one: our police captured 3 of 3 against the kit's
sparring peer, whose opener is slower and lands after the bind.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.sdk.handshake_setup import _bind_expected_role

TERMS: dict[str, Any] = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
    "emit_intensity": 0.9, "min_center_intensity": 0.5, "max_steps": 35,
    "barriers_max": 14, "setting": "New York", "hint_max_words": 15,
    "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 6,
}
IDENTITY = {"group_id": "najamjad"}


class _Guard:
    def __init__(self) -> None:
        self.expected_sender = ""
        self.expected_token = ""
        self.binds: list[str] = []

    def bind(self, opponent_id: str, config_sha256: str = "", game_uid: str = "") -> None:
        self.expected_sender = opponent_id
        self.expected_token = f"{config_sha256[:8]}:{game_uid[:8]}"
        self.binds.append(opponent_id)


class _Inboxes:
    def __init__(self) -> None:
        self.guard = _Guard()


class _Manager:
    def __init__(self, group: str = "imreeyal") -> None:
        self._group = group

    def get(self, key: str, default: Any = None) -> Any:
        return self._group if key == "network.opponent_group_id" else default


def _events() -> tuple[list[dict], Any]:
    seen: list[dict] = []
    return seen, seen.append


def test_playing_police_expects_a_thief_before_the_exchange() -> None:
    """The case that failed: we are police, so their opener says 'thief'."""
    inboxes = _Inboxes()
    _, emit = _events()

    _bind_expected_role(inboxes, _Manager(), TERMS, IDENTITY, "police", emit)

    assert inboxes.guard.expected_sender == "thief"
    assert inboxes.guard.expected_token, "the token must bind too, or a stranger passes"


def test_playing_thief_expects_a_police() -> None:
    """The mirror, which always worked because we open and nothing can race."""
    inboxes = _Inboxes()
    _, emit = _events()

    _bind_expected_role(inboxes, _Inboxes.__init__ and _Manager(), TERMS, IDENTITY, "thief", emit)

    assert inboxes.guard.expected_sender == "police"


def test_the_early_token_matches_what_the_later_bind_derives() -> None:
    """Both binds must agree, or the correction would reject the peer instead.

    The early bind reads the opponent id from the card and the later one from
    their declared identity. For an honest peer those are the same string, so
    the token is the same — which is what makes binding early safe rather than a
    guess we have to undo.
    """
    from najamjad_agent.negotiation.contract import contract_hash, derive_game_ids

    inboxes = _Inboxes()
    _, emit = _events()
    _bind_expected_role(inboxes, _Manager(), TERMS, IDENTITY, "police", emit)

    _, uid = derive_game_ids(dict(TERMS), "najamjad", "imreeyal")
    expected = f"{contract_hash(dict(TERMS))[:8]}:{uid[:8]}"

    assert inboxes.guard.expected_token == expected


def test_an_unknown_opponent_leaves_the_guard_open_rather_than_wrong() -> None:
    """Unbound admits. That costs a guard we never had; binding wrong costs the game."""
    for group in ("", "them"):
        inboxes = _Inboxes()
        seen, emit = _events()

        _bind_expected_role(inboxes, _Manager(group), TERMS, IDENTITY, "police", emit)

        assert inboxes.guard.expected_sender == ""
        assert any(e["event"] == "session.early_bind_skipped" for e in seen)


def test_the_bind_happens_before_the_exchange_in_the_real_handshake() -> None:
    """Ordering is the entire fix, so it is pinned against the source."""
    from pathlib import Path

    source = Path("src/najamjad_agent/sdk/handshake_setup.py").read_text(encoding="utf-8")
    early = source.index("_bind_expected_role(inboxes, manager")
    exchange = source.index("peer = exchange_agreement(")
    late = source.index("_bind_session(inboxes, session, declared")

    assert early < exchange < late, "the guard must expect their role before the exchange"
