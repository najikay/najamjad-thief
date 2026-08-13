"""Our agreement digest must equal the opponent's, and now it is pinned to one.

Rule 35 voids a match for **both** teams when the two reports contradict, and
`mutual_agreement.sha256` is the one field designed to be identical on both
machines. Ours was not. We hashed `{game_id, game_uid, groups, sub_games}` with
compact separators; the lecturer's reference signs `{game_id, aggregate,
sub_games}` with `json.dumps(sort_keys=True, ensure_ascii=False)` and no
`separators` argument — Python's spaced defaults.

Two deviations, either one sufficient. Everything about a series could agree and
only the signature over it differ, which is exactly what happened: imreeyal's
opponents matched their digest byte-equal in three of four counted series while
ours matched nobody, including — almost certainly — our own first counted match.

The oracle below is not our arithmetic. `38b22e02…` is the value imreeyal
published for the 2026-08-13 friendly, independently reproduced from
`report/emit.py` in the reference before either side changed anything.
"""

from __future__ import annotations

from najamjad_agent.reporting.agreement import agreement_hash, symmetric_outcome

GAME_ID = "imreeyal-vs-najamjad"
GAME_UID = "0109494f-4e63-cb2d-d402-741e1468bdbf"
GROUPS = ("imreeyal", "najamjad")

#: The 2026-08-13 friendly, as both teams' result files record it.
SUB_GAMES = [
    {"sub_game_number": n,
     "roles": {"imreeyal": police, "najamjad": thief},
     "result": result,
     "winner_group": "najamjad",
     "score": {"imreeyal": 5, "najamjad": ours}}
    for n, police, thief, result, ours in (
        (1, "police", "thief", "survival", 10),
        (2, "thief", "police", "capture", 20),
        (3, "police", "thief", "survival", 10),
        (4, "thief", "police", "capture", 20),
        (5, "police", "thief", "survival", 10),
        (6, "thief", "police", "capture", 20),
    )
]
#: Published by imreeyal for that series, from an independent implementation.
THEIR_PUBLISHED = "38b22e02393d3e9908a4d8bd4d1544c673f922ccd1af1e448ce58c3b525a4262"


def test_we_reproduce_the_opponents_published_digest() -> None:
    """The only assertion that matters: their number, from our code."""
    assert agreement_hash(GAME_ID, GAME_UID, GROUPS, SUB_GAMES) == THEIR_PUBLISHED


def test_the_preimage_is_exactly_the_reference_three_keys() -> None:
    """A fourth key is a different digest, however symmetric it looks.

    `game_uid` and `groups` are both facts the peers share, which is why
    including them seemed harmless — and why this needs pinning rather than
    reasoning about.
    """
    outcome = symmetric_outcome(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)

    assert set(outcome) == {"game_id", "aggregate", "sub_games"}
    assert set(outcome["sub_games"][0]) == {
        "sub_game_number", "roles", "result", "winner_group", "score"
    }


def test_the_aggregate_is_the_five_keys_the_reference_signs() -> None:
    outcome = symmetric_outcome(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)

    assert set(outcome["aggregate"]) == {
        "total_score", "sub_games_won", "ties", "winner_group", "series_tie"
    }
    assert outcome["aggregate"]["total_score"] == {"imreeyal": 30, "najamjad": 90}
    assert outcome["aggregate"]["sub_games_won"] == {"imreeyal": 0, "najamjad": 6}
    assert outcome["aggregate"]["winner_group"] == "najamjad"
    assert outcome["aggregate"]["series_tie"] is False


def test_the_digest_does_not_depend_on_which_side_computes_it() -> None:
    """Swapped group order must give one number, or peers can never agree."""
    assert agreement_hash(GAME_ID, GAME_UID, ("najamjad", "imreeyal"), SUB_GAMES) == (
        agreement_hash(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)
    )


def test_a_series_tie_pays_the_bonus_inside_the_signed_aggregate() -> None:
    """The reference adds `tie_score` to the totals *before* signing them.

    Applying the bonus anywhere else would hash differently on the two machines
    for the same tied series — the same class of bug, one level down.
    """
    drawn = [
        {"sub_game_number": 1, "roles": {"a": "police", "b": "thief"},
         "result": "capture", "winner_group": "a", "score": {"a": 20, "b": 5}},
        {"sub_game_number": 2, "roles": {"a": "thief", "b": "police"},
         "result": "capture", "winner_group": "b", "score": {"a": 5, "b": 20}},
    ]

    aggregate = symmetric_outcome("a-vs-b", "uid", ("a", "b"), drawn)["aggregate"]

    assert aggregate["series_tie"] is True
    assert aggregate["winner_group"] is None
    assert aggregate["total_score"] == {"a": 27, "b": 27}, "25 each plus the tie bonus"
