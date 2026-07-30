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


# ------------------------------------------------- the agreement we assert


def filed_with(tmp_path, audit: str) -> dict:
    """One filed match whose only variable is the audit verdict."""
    import json

    from najamjad_agent.reporting.filing import MatchFiler

    class Outcome:
        our_score, their_score = 20, 5

    class Result:
        total_score = {"a": 20, "b": 5}
        sub_games_won = {"a": 1, "b": 0}
        ties = 0
        winner_group = "a"
        series_tie = False
        tie_award = None

    def block(group: str) -> dict:
        return {"group_id": group, "group_name": group.title(), "members": ["A", "B"],
                "repos": {"cop": "https://example.invalid/repo"}}

    games = [{"sub_game": 1, "role": "police", "end_reason": "capture", "steps": 9,
              "audit": audit,
              "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c" * 64}]}]
    written = MatchFiler(tmp_path, "a-vs-b", "uid", ("a", "b")).file_match(
        games, [Outcome()], Result(),
        {"board_and_agents": {}, "movement_and_barriers": {}, "scoring": {}, "pheromones": {}},
        "x" * 64, {"a": block("a"), "b": block("b")},
    )
    from pathlib import Path

    return json.loads(Path(written["result"]).read_text(encoding="utf-8"))


def test_mutual_agreement_is_earned_not_assumed(tmp_path):
    """`confirmed` defaulted to True and no caller ever passed it.

    So every report we filed asserted mutual agreement with the opponent
    without checking anything — and rules 33-35 make contradictory reports
    void both sides. It happened to be true in the first real match, which is
    luck rather than verification.
    """
    assert filed_with(tmp_path, "Verified OK")["mutual_agreement"]["confirmed"] is True


def test_a_tampered_log_is_not_agreement(tmp_path):
    """The case the old default got exactly backwards: a report claiming we
    agreed with an opponent whose log did not verify."""
    assert filed_with(tmp_path, "TAMPERED")["mutual_agreement"]["confirmed"] is False


def test_a_skipped_audit_is_not_agreement(tmp_path):
    """Silence is not consent. The nonces were never revealed, so nothing was
    verified and there is nothing to confirm."""
    assert filed_with(tmp_path, "AUDIT SKIPPED")["mutual_agreement"]["confirmed"] is False


def test_a_disputed_outcome_is_not_agreement(tmp_path):
    """The agreement the protocol actually affords, and it ran one-way.

    Each side states how it thinks a mini-game ended inside its audit envelope
    (`result_claim`). We always sent ours and never read theirs, so the only
    channel the two agents have for agreeing on an outcome was used in one
    direction — and `mutual_agreement.confirmed` could report agreement with
    an opponent who had said something different. Rules 33-35 void both teams
    for exactly that.
    """
    import json
    from pathlib import Path

    from najamjad_agent.reporting.filing import MatchFiler

    class Outcome:
        our_score, their_score = 20, 5

    class Result:
        total_score = {"a": 20, "b": 5}
        sub_games_won = {"a": 1, "b": 0}
        ties = 0
        winner_group = "a"
        series_tie = False
        tie_award = None

    def block(group: str) -> dict:
        return {"group_id": group, "group_name": group.title(), "members": ["A"],
                "repos": {"cop": "https://example.invalid/repo"}}

    games = [{"sub_game": 1, "role": "police", "end_reason": "capture", "steps": 9,
              "audit": "Verified OK", "disputed": True, "their_claim": "survival",
              "records": [{"payload": {"step": 1}, "nonce": "n", "commit": "c" * 64}]}]
    written = MatchFiler(tmp_path, "a-vs-b", "uid", ("a", "b")).file_match(
        games, [Outcome()], Result(),
        {"board_and_agents": {}, "movement_and_barriers": {}, "scoring": {}, "pheromones": {}},
        "x" * 64, {"a": block("a"), "b": block("b")},
    )
    result = json.loads(Path(written["result"]).read_text(encoding="utf-8"))

    assert result["mutual_agreement"]["confirmed"] is False, (
        "their log verified, but they said the game ended differently"
    )


def test_a_matching_claim_leaves_agreement_intact():
    """Reading their claim must not turn every clean match into a dispute."""
    from dataclasses import replace

    from najamjad_agent.domain.audit import AuditReport

    report = replace(AuditReport(passed=True), their_claim="capture")

    assert report.disputed is False


def test_an_absent_claim_is_not_a_dispute():
    """An opponent who revealed nothing has said nothing to disagree with —
    that is `AUDIT SKIPPED`, a different verdict with a different meaning."""
    from najamjad_agent.domain.audit import AuditReport

    assert AuditReport(passed=False, skipped=True).disputed is False
