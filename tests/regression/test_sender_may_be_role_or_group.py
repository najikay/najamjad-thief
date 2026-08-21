"""`sender` means the role to some peers and the group id to others (T-2713).

`SessionGuard` bound the peer's **role** as the only acceptable `sender`, and
that held for four counted series because three teams put exactly that there —
"police" or "thief", 5,239 messages across our two event logs. Then nis-yar1 put
their **group id** in it, which is the more natural reading of a field called
`sender` and is precisely what we had asked them for, and we rejected every
message: `sender 'nis-yar1' is not the negotiated opponent 'police'`.

The handshake locked and then the game could not start. From their side it looked
like repeated HTTP 400s, which they reasonably diagnosed as stale sessions — our
own log named the real cause and theirs could not.

So both forms are accepted. The guard's job is to keep a *third party* out, and
neither the role we negotiated nor the group id we signed with is a third party;
the session token is what actually proves "we negotiated together".
"""

from types import SimpleNamespace

from najamjad_agent.net.session_guard import SessionGuard, session_token

CONFIG_SHA = "a284082dfb1572236f1b614d29295a99625539c7d33a096f7f8921bafbc3d08d"
GAME_UID = "1753965a-1f98-d3fb-4241-0245786936c8"


def guard() -> SessionGuard:
    one = SessionGuard()
    one.bind("police", CONFIG_SHA, GAME_UID, group_id="nis-yar1")
    return one


def message(sender: str = "", token: str = "") -> SimpleNamespace:
    return SimpleNamespace(sender=sender, session_token=token)


def test_the_role_is_accepted_as_it_always_was() -> None:
    """Four counted series depended on this; it must not regress."""
    assert guard().check(message("police")) is None


def test_the_group_id_is_accepted_too() -> None:
    """The case that stopped a live friendly on 2026-08-17."""
    assert guard().check(message("nis-yar1")) is None


def test_an_absent_sender_still_passes() -> None:
    """Reference-implementation peers send none at all."""
    assert guard().check(message()) is None


def test_a_third_party_is_still_refused() -> None:
    """The guard's actual purpose, unchanged."""
    refusal = guard().check(message("some-other-team"))

    assert refusal is not None
    assert "some-other-team" in refusal
    assert "police" in refusal and "nis-yar1" in refusal, "name both accepted forms"


def test_an_unbound_guard_admits_anybody() -> None:
    """Before negotiation any peer may introduce itself; that is how a match starts."""
    assert SessionGuard().check(message("whoever")) is None


def test_a_bad_token_is_still_refused_whichever_name_is_used() -> None:
    """The token is what proves we negotiated together, and it still binds."""
    for name in ("police", "nis-yar1"):
        refusal = guard().check(message(name, token="0" * 32))
        assert refusal is not None and "token" in refusal


def test_the_right_token_passes_with_either_name() -> None:
    good = session_token(CONFIG_SHA, GAME_UID)

    for name in ("police", "nis-yar1"):
        assert guard().check(message(name, token=good)) is None


def test_releasing_forgets_both_names() -> None:
    one = guard()
    one.release()

    assert one.bound is False
    assert one.check(message("anyone-at-all")) is None


def test_binding_without_a_group_id_keeps_the_old_behaviour_exactly() -> None:
    """An older call site, or a peer whose group we never learned."""
    one = SessionGuard()
    one.bind("thief", CONFIG_SHA, GAME_UID)

    assert one.check(message("thief")) is None
    assert one.check(message("nis-yar1")) is not None


def test_cop_is_police_wearing_its_other_name() -> None:
    """bestteam's turns arrived as `sender: 'cop'` on 2026-08-18 and were
    refused against an expected 'police' — one role, two spellings, and our
    own config parser accepts both. The guard now does too, both ways."""
    assert guard().check(message("cop")) is None

    flipped = SessionGuard()
    flipped.bind("cop", CONFIG_SHA, GAME_UID, group_id="bestteam")
    assert flipped.check(message("police")) is None
    assert flipped.check(message("bestteam")) is None
    assert flipped.check(message("thief")) is not None
