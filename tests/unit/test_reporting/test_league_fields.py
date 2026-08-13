"""The league fields a grader reads, and the key name a peer reads them by.

Rule 38 judges counted-match declarations on *mutual consistency between the two
teams' files* and treats a false one as project-level. Ours were not there to be
consistent with: `final_result` carried none of the three template fields, and
our handshake identity declared the count under `counted_matches_played` where
the league's readers look for `counted_games_played`.

The consequence was not ours to see. imreeyal's runner builds its league block
from our identity, found neither key it knew, and filed `najamjad: 0` against a
truth of 1 — a wrong number about us, in an honest opponent's report. Their
counted file would have said 0 where the truth is 2.
"""

from __future__ import annotations

from najamjad_agent.reporting.result_blocks import league_block

OURS, THEIRS = "najamjad", "imreeyal"


def _blocks(our_count: int, their_count: int, their_key: str = "counted_games_played",
            met: list[str] | None = None) -> dict[str, dict]:
    return {
        OURS: {"counted_matches_played": our_count, "counted_games_played": our_count,
               "opponents_already_counted": met or []},
        THEIRS: {their_key: their_count, "opponents_already_counted": []},
    }


def test_a_counted_series_counts_itself() -> None:
    """`including_this` is in the name: the series being filed is one of them."""
    block = league_block(_blocks(1, 4), counted=True, groups=(OURS, THEIRS))

    assert block["games_played_including_this"] == {OURS: 2, THEIRS: 5}


def test_a_friendly_does_not_count_itself() -> None:
    """An uncounted series must not inflate either side's total."""
    block = league_block(_blocks(1, 4), counted=False, groups=(OURS, THEIRS))

    assert block["games_played_including_this"] == {OURS: 1, THEIRS: 4}


def test_either_spelling_of_the_count_is_read() -> None:
    """The defect itself: assuming our own key name put a zero in their file."""
    for key in ("counted_games_played", "counted_matches_played"):
        block = league_block(_blocks(1, 4, their_key=key), counted=True, groups=(OURS, THEIRS))

        assert block["games_played_including_this"][THEIRS] == 5, f"{key} was not read"


def test_a_peer_declaring_nothing_reads_as_zero_not_as_a_crash() -> None:
    """A silent peer is a number we do not know, not a reason to fail filing."""
    blocks = {OURS: {"counted_games_played": 1, "opponents_already_counted": []}, THEIRS: {}}

    block = league_block(blocks, counted=True, groups=(OURS, THEIRS))

    assert block["games_played_including_this"] == {OURS: 2, THEIRS: 1}


def test_first_meeting_is_true_until_one_side_has_counted_the_other() -> None:
    assert league_block(_blocks(1, 4), True, (OURS, THEIRS))["first_meeting_between_groups"]

    met = league_block(_blocks(1, 4, met=[THEIRS]), True, (OURS, THEIRS))

    assert met["first_meeting_between_groups"] is False


def test_the_diversity_reward_is_never_claimed_in_our_own_file() -> None:
    """All-false is always legal; claiming it for ourselves is not ours to do.

    The reward belongs to the winner of a first meeting, and a false claim here
    is the same rule-38 exposure pointing the other way.
    """
    block = league_block(_blocks(1, 4), counted=True, groups=(OURS, THEIRS))

    assert block["diversity_reward_applied"] == {OURS: False, THEIRS: False}


def test_the_declaration_carries_both_spellings_of_the_count() -> None:
    """Both keys, one integer, from one tracker — they cannot disagree."""
    from najamjad_agent.negotiation.counted_games import CountedGames

    declaration = CountedGames(path=None, opponents=["uoh-ay26"]).declaration()

    assert declaration["counted_matches_played"] == declaration["counted_games_played"] == 1
