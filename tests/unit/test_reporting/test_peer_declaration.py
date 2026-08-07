"""The opponent's own claims, read rather than invented.

Six mini-games against uoh-sqak were filed with `github_commit: "unknown"` and
`tokens: 0` for them. Neither was a lookup that failed: the commit came from a
`their_commit` key nothing in the project ever wrote, and the token figure was
a literal `0` in the row builder, so an honestly declaring peer would still
have been reported as having spent nothing.
"""

from najamjad_agent.reporting.peer_declaration import UNKNOWN_COMMIT, peer_facts
from najamjad_agent.reporting.step_zero import RECORD_TYPE


def _game(sub_game: int, commit: str = "abc1234", tokens: int = 0, extra: list | None = None):
    """A played record carrying the opponent's revealed step-0 declaration."""
    records = [
        {
            "payload": {
                "step": 0,
                "type": RECORD_TYPE,
                "github_commit": commit,
                "tokens_total": tokens,
            },
            "nonce": "n",
            "commit": "c",
        }
    ]
    return {"sub_game": sub_game, "their_records": records + (extra or [])}


def test_their_commit_comes_from_their_declaration() -> None:
    """Rule 49: the report names the commit each side actually played."""
    facts = peer_facts([_game(1, commit="deadbee")])

    assert facts[1]["commit"] == "deadbee"


def test_a_game_cost_is_the_gap_between_two_running_totals() -> None:
    """The subtle half. `tokens_total` is an opening balance, not a price.

    Read directly, game three would be billed its opening balance of 900 and
    the series total would be a sum of prefixes — larger than anything anyone
    spent.
    """
    facts = peer_facts([_game(1, tokens=0), _game(2, tokens=400), _game(3, tokens=900)])

    assert facts[1]["tokens"] == 400
    assert facts[2]["tokens"] == 500


def test_the_last_mini_game_reports_no_cost_rather_than_a_guess() -> None:
    """Nothing declares it: there is no seventh declaration to subtract from.

    Understating one game is a smaller error than inventing a figure, and the
    alternative — carrying the previous game's cost forward — would state a
    number the opponent never claimed in a report they also file.
    """
    facts = peer_facts([_game(1, tokens=0), _game(2, tokens=400)])

    assert facts[2]["tokens"] == 0


def test_a_peer_who_declares_nothing_still_files(_records=None) -> None:
    """Most opponents emit no step-0 at all, and that is not an error.

    It must degrade to "absent" — `"unknown"` and 0 — never to an exception,
    because the report is written after six games have already been played.
    """
    facts = peer_facts([{"sub_game": 1, "their_records": []}, {"sub_game": 2}])

    assert facts[1] == {"commit": UNKNOWN_COMMIT, "tokens": 0}
    assert facts[2]["commit"] == UNKNOWN_COMMIT


def test_the_declaration_is_found_by_type_not_by_position() -> None:
    """A peer may order their reveal differently without thereby lying.

    Matching on `records[0]` would read a move record as a declaration and
    report its absent commit as unknown while one sat two entries later.
    """
    moves = [{"payload": {"step": 1, "move": "MOVE:N"}, "nonce": "n", "commit": "c"}]
    game = _game(1, commit="feedface")
    game["their_records"] = moves + game["their_records"]

    assert peer_facts([game])[1]["commit"] == "feedface"


def test_a_meter_that_runs_backwards_cannot_subtract_from_the_series() -> None:
    """Clamped at zero: a peer resetting its meter between games is not a refund."""
    facts = peer_facts([_game(1, tokens=900), _game(2, tokens=0)])

    assert facts[1]["tokens"] == 0


def test_unreadable_totals_are_dropped_not_raised() -> None:
    """Their claim arrives in a shape we do not control (cf. `normalise_spec`)."""
    facts = peer_facts([_game(1, tokens="lots"), _game(2, tokens=400)])  # type: ignore[arg-type]

    assert facts[1]["tokens"] == 0


def test_facts_are_keyed_by_sub_game_not_by_order() -> None:
    """The games list and the rows it feeds are ordered independently.

    Zipping two lists is how a report ends up attributing game five's spend to
    game two, which is worse than reporting neither.
    """
    facts = peer_facts([_game(3, commit="three"), _game(1, commit="one")])

    assert facts[3]["commit"] == "three"
    assert facts[1]["commit"] == "one"
