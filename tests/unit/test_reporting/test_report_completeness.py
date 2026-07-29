"""Fields the report must carry, each one missing from a real match (T-2439).

A first live match against another machine produced a report that was correct
about the *game* and incomplete about everything around it. Every defect below
was invisible to the existing tests because each field was present and empty,
and the drift test compared key sets rather than descending into them.

The stakes are why these are pinned: an incomplete report is what lost marks on
the previous assignment, and rule 35 zeroes both teams for a report the
lecturer cannot use.
"""

from najamjad_agent.domain.game_state import TurnFacts
from najamjad_agent.domain.scoring import aggregate_series
from najamjad_agent.reporting.result_blocks import (
    declaration_group,
    final_result_block,
    series_tokens,
)

GROUPS = ("najamjad", "najamjad-b")


def tied_series():
    scores = [{"najamjad": 20, "najamjad-b": 5} if n % 2 else {"najamjad": 5, "najamjad-b": 20}
              for n in range(1, 7)]
    return aggregate_series(scores, GROUPS, tie_score=2)


def test_the_turn_facts_carry_the_mini_game_number():
    """Without it every LLM call was billed to sub-game 0.

    The meter held ~7,300 tokens after a six-game series while the report said
    each game cost nothing and the series total was zero — the speaker read
    `facts.sub_game`, and `TurnFacts` had no such field, so `getattr` returned
    the default forever.
    """
    assert "sub_game" in TurnFacts.__dataclass_fields__


def test_series_tokens_sum_the_per_game_numbers():
    rows = [{"tokens": {"najamjad": 1200, "najamjad-b": 0}},
            {"tokens": {"najamjad": 1150, "najamjad-b": 0}}]

    assert series_tokens(rows) == {"najamjad": 2350, "najamjad-b": 0}


def test_a_tied_series_states_the_award():
    """`aggregate_series` computed `tie_award` and the schema had nowhere to
    put it, so we told the lecturer a series tied and never stated the award
    the book sets for it (PAGE 87, Appendix F: 2)."""
    block = final_result_block(tied_series())

    assert block["series_tie"] is True
    assert block["winner_group"] is None
    assert block["tie_award"] == 2


def test_a_decided_series_omits_the_award_entirely():
    """The lecturer's sample was not a tie and carries no such key. A null
    field a grader does not expect is a different kind of noise."""
    decided = aggregate_series([{"najamjad": 20, "najamjad-b": 5}], GROUPS, tie_score=2)

    assert "tie_award" not in final_result_block(decided)


def test_the_declaration_finds_the_hardware_under_either_name():
    """The wire calls it `spec` because that is what the reference reads; the
    artifact schema calls it `hardware_spec`. Nothing mapped between them, so
    every Step-0 fairness declaration (rule 24) shipped `hardware_spec: null`
    while the identity beside it held the whole spec."""
    block = declaration_group({"group_id": "x", "spec": {"os": "Windows 10", "ram_gb": 7.9}})

    assert block["hardware_spec"] == {"os": "Windows 10", "ram_gb": 7.9}


def test_an_identity_that_already_uses_the_artifact_name_is_untouched():
    block = declaration_group({"group_id": "x", "hardware_spec": {"ram_gb": 16.0}})

    assert block["hardware_spec"] == {"ram_gb": 16.0}


def test_a_missing_spec_does_not_invent_one():
    """Absent hardware must stay absent rather than become an empty object a
    grader would read as a declared spec."""
    assert declaration_group({"group_id": "x"}).get("hardware_spec") is None


def test_the_emailed_result_carries_both_teams_repositories():
    """Chapter 9.4 and rule 49: all four links appear in the JSON attached to
    the match-end email, and only the result artifact is emailed.

    `links` holds sibling artifact *filenames*, which is a different thing.
    The lecturer's sample carries no repository links at all — this is an
    addition rather than parity, and erring toward including a mandated field
    the sample omits is the safer direction.
    """
    from najamjad_agent.reporting.result_blocks import repository_links

    links = repository_links({
        "najamjad": {"repos": {"cop": "https://github.com/najikay/najamjad-cop",
                               "thief": "https://github.com/najikay/najamjad-thief"}},
        "najamjad-b": {"repos": {"cop": "https://github.com/najikay/najamjad-cop",
                                 "thief": "https://github.com/najikay/najamjad-thief"}},
    })

    assert set(links) == {"najamjad", "najamjad-b"}
    assert sum(len(v) for v in links.values()) == 4, "four links, two per team"


def test_a_team_that_declared_no_repositories_is_omitted():
    """An empty link reads as a broken repository; absence reads as absence."""
    from najamjad_agent.reporting.result_blocks import repository_links

    links = repository_links({"a": {"repos": {"cop": "https://x.invalid"}}, "b": {"repos": {}}})

    assert set(links) == {"a"}
