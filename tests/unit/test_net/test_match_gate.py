"""One match at a time (T-2454).

Written against a real failure rather than an imagined one: against ahk-yosi
their hosted peer retried our endpoint on a loop while we dialled theirs, we
accepted 58 inbound handshakes during a six-game series, and every mini-game
scored 0-0 technical because two games shared one inbox.

The tests below are mostly about the *shape* of the refusal. Closing the gate
is easy; closing it in a way that does not forfeit a match against a
well-behaved opponent whose clock runs a little ahead of ours is the part
worth pinning down.
"""

from najamjad_agent.net.match_gate import BUSY_REASON, MatchGate


def test_a_listening_agent_can_be_challenged():
    """Open by default — the peer who dials second must be able to start."""
    assert MatchGate().open is True
    assert MatchGate().refuse() is None


def test_a_handshake_during_a_mini_game_is_refused():
    gate = MatchGate()

    gate.begin_sub_game()

    assert gate.open is False
    assert gate.refuse() == BUSY_REASON


def test_the_gate_reopens_at_the_boundary():
    """Re-handshake before every mini-game is the normal protocol."""
    gate = MatchGate()
    gate.begin_sub_game()

    gate.end_sub_game()

    assert gate.refuse() is None


def test_reopening_twice_is_harmless():
    """`end_sub_game` runs from a `finally`; it must tolerate a double call.

    A gate stuck shut is worse than the bug it fixes: the agent would look
    healthy and refuse every opponent for the rest of the series.
    """
    gate = MatchGate()
    gate.begin_sub_game()

    gate.end_sub_game()
    gate.end_sub_game()

    assert gate.open is True


def test_the_refusal_is_recorded_for_the_operator():
    """A refused handshake is a fact about the opponent, not an internal detail.

    Silence here would have made the ahk-yosi diagnosis take as long the
    second time: the log has to show that someone tried.
    """
    seen: list[dict] = []
    gate = MatchGate(emit=seen.append)
    gate.begin_sub_game()

    gate.refuse()

    assert [event["event"] for event in seen] == ["handshake.refused"]


def test_an_allowed_handshake_is_not_noise():
    """Only refusals are worth an event; the happy path stays quiet."""
    seen: list[dict] = []
    gate = MatchGate(emit=seen.append)

    gate.refuse()

    assert seen == []
