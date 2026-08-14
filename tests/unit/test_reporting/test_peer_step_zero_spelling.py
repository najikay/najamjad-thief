"""Read a peer's step-0 record by what it is, not by what *we* call it.

Two fields of the result artifact belong to the other team and cannot be
computed on our side: the commit they played with (rules 49, 53) and what the
series cost them (rule 54). Both live in their step-0 declaration.

We looked for `type == "system_spec"`, which is our own spelling and the
reference's. **vibecode call theirs `step_zero`.** So the lookup missed on every
mini-game of the 2026-08-14 series, and six filed sub-games recorded their commit
as `"unknown"` while the real value — `a3be8b4e…` for their thief, `96ac5a72…`
for their cop — sat in our own log the entire time.

That is the `counted_games_played` bug wearing a different mask: a field read
under the name we happen to use rather than the name the wire happens to carry.
That one put a wrong number in an honest opponent's report; this one put a wrong
string in ours.
"""

from __future__ import annotations

from najamjad_agent.reporting.peer_declaration import UNKNOWN_COMMIT, peer_facts

THEIR_THIEF = "a3be8b4e70c548e33d97464296d9751d319bdd21"


def _game(sub_game: int, payload: dict) -> dict:
    return {"sub_game": sub_game, "their_records": [{"payload": payload}]}


def test_their_spelling_is_read() -> None:
    """`step_zero`, as vibecode actually send it."""
    games = [_game(1, {"type": "step_zero", "step": 0, "github_commit": THEIR_THIEF})]

    assert peer_facts(games)[1]["commit"] == THEIR_THIEF


def test_our_own_spelling_still_works() -> None:
    """`system_spec` is ours and the reference's, and must not regress."""
    games = [_game(1, {"type": "system_spec", "step": 0, "github_commit": THEIR_THIEF})]

    assert peer_facts(games)[1]["commit"] == THEIR_THIEF


def test_an_unknown_spelling_falls_back_to_the_step_number() -> None:
    """A peer may call it anything; step 0 is structural.

    The fallback is second, not first, so a peer sending several records at
    step 0 still gets the one that says what it is.
    """
    games = [_game(1, {"type": "whatever-they-like", "step": 0, "github_commit": THEIR_THIEF})]

    assert peer_facts(games)[1]["commit"] == THEIR_THIEF


def test_a_typed_record_beats_a_bare_step_zero() -> None:
    games = [{
        "sub_game": 1,
        "their_records": [
            {"payload": {"step": 0, "github_commit": "wrong-one"}},
            {"payload": {"type": "step_zero", "step": 0, "github_commit": THEIR_THIEF}},
        ],
    }]

    assert peer_facts(games)[1]["commit"] == THEIR_THIEF


def test_a_peer_that_declares_nothing_is_still_filable() -> None:
    """Most peers declare nothing, and rule 35 punishes not reporting."""
    games = [_game(1, {"step": 4, "position": [1, 1]})]

    assert peer_facts(games)[1]["commit"] == UNKNOWN_COMMIT
