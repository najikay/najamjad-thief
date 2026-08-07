"""Tests for result reconciliation — the step that makes `confirmed` truthful.

Rule 35 voids a match for BOTH teams on contradictory reports, so the expensive
failure is disagreeing silently.
"""

from najamjad_agent.reporting.agreement import agreement_hash, symmetric_outcome
from najamjad_agent.reporting.reconcile import (
    AGREED,
    MISMATCH,
    NO_REPLY,
    our_summary,
    reconcile,
)

GAME_ID = "najamjad-vs-rival"
GAME_UID = "uid-123"
GROUPS = ("najamjad", "rival")
SUB_GAMES = [
    {
        "sub_game_number": 1,
        "result": "capture",
        "winner_group": "najamjad",
        "score": {"najamjad": 20, "rival": 5},
    },
    {
        "sub_game_number": 2,
        "result": "survival",
        "winner_group": "rival",
        "score": {"najamjad": 5, "rival": 10},
    },
]


def _summary(sub_games=None):
    return our_summary(GAME_ID, GAME_UID, GROUPS, sub_games or SUB_GAMES)


def test_both_peers_compute_the_same_signature() -> None:
    """The whole point: our hash and theirs must match byte-for-byte."""
    ours = agreement_hash(GAME_ID, GAME_UID, ("najamjad", "rival"), SUB_GAMES)
    theirs = agreement_hash(GAME_ID, GAME_UID, ("rival", "najamjad"), SUB_GAMES)
    assert ours == theirs


def test_the_symmetric_outcome_excludes_per_peer_facts() -> None:
    """Hashing our token spend or commit would guarantee two different hashes."""
    outcome = symmetric_outcome(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)
    flat = str(outcome)
    assert "tokens" not in flat
    assert "github_commit" not in flat
    assert outcome["groups"] == ["najamjad", "rival"], "group order is normalised"


def test_roles_are_included_because_keyed_by_group_they_are_symmetric() -> None:
    """Excluded once, and that was over-caution with a real cost.

    A role is per-peer only when recorded as "ours" and "theirs". Keyed by
    group id both peers build the identical mapping, so it hashes the same on
    both machines — which is the only property that matters here.

    The reference includes roles in its preimage. Omitting them made our digest
    differ from a reference-derived opponent's for the very same series, and
    under rule 35 a differing `sha256` is indistinguishable from contradictory
    reports. Being more cautious than the reference cut the wrong way: it cost
    us agreement with the peers we most need to agree with.
    """
    outcome = symmetric_outcome(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)

    assert "roles" in outcome["sub_games"][0]
    # The property that makes it safe: order-independent, both directions.
    assert agreement_hash(GAME_ID, GAME_UID, ("najamjad", "rival"), SUB_GAMES) == agreement_hash(
        GAME_ID, GAME_UID, ("rival", "najamjad"), SUB_GAMES
    )


def test_matching_summaries_are_agreed() -> None:
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, _summary())
    assert result.status == AGREED
    assert result.confirmed is True
    assert result.may_send


def test_agreement_is_a_real_boolean_not_a_default() -> None:
    """A6's `agreement: null` came from never running this step."""
    agreed = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, _summary())
    disputed = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, _summary([SUB_GAMES[0]]))
    assert agreed.confirmed is True
    assert disputed.confirmed is False


def test_a_disagreement_is_reported_field_by_field() -> None:
    theirs = _summary(
        [
            {**SUB_GAMES[0], "score": {"najamjad": 5, "rival": 20}},
            SUB_GAMES[1],
        ]
    )
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert result.status == MISMATCH
    assert not result.confirmed
    assert any("score" in difference for difference in result.differences)


def test_a_disagreement_holds_the_send_for_an_operator() -> None:
    """A wrong-but-confident report is worse than a late one."""
    theirs = _summary([{**SUB_GAMES[0], "winner_group": "rival"}, SUB_GAMES[1]])
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert not result.may_send
    alert = result.operator_alert()
    assert alert is not None
    assert alert["event"] == "result.mismatch"
    assert alert["ours"] and alert["theirs"]


def test_a_differing_game_count_is_caught() -> None:
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, _summary([SUB_GAMES[0]]))
    assert result.status == MISMATCH
    assert any("length" in difference for difference in result.differences)


def test_silence_from_the_opponent_still_permits_reporting() -> None:
    """Rule 35 punishes not reporting too, so their silence must not stop us."""
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, None)
    assert result.status == NO_REPLY
    assert result.may_send
    assert result.confirmed is False, "we cannot claim agreement we never got"


def test_an_agreed_result_raises_no_operator_alert() -> None:
    assert reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, _summary()).operator_alert() is None


def test_a_summary_without_a_hash_falls_back_to_field_comparison() -> None:
    """An opponent implementation may not send our signature field."""
    theirs = {"outcome": symmetric_outcome(GAME_ID, GAME_UID, GROUPS, SUB_GAMES)}
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert result.status == MISMATCH
    assert "no field-level difference" in result.differences[0]


def test_the_summary_we_send_carries_hash_and_outcome() -> None:
    summary = _summary()
    assert len(summary["sha256"]) == 64
    assert summary["outcome"]["game_uid"] == GAME_UID


def test_sub_game_order_does_not_affect_the_signature() -> None:
    """Two peers may hold their rows in different orders and still agree."""
    reversed_rows = list(reversed(SUB_GAMES))
    assert agreement_hash(GAME_ID, GAME_UID, GROUPS, SUB_GAMES) == agreement_hash(
        GAME_ID, GAME_UID, GROUPS, reversed_rows
    )


def test_a_stale_hash_beside_fresh_data_is_not_agreement() -> None:
    """A signature is only evidence if it describes the data sent with it."""
    theirs = _summary()
    theirs["outcome"]["sub_games"][0]["winner_group"] = "rival"
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert result.status == MISMATCH
    assert not result.confirmed
    assert "signature matches ours but their outcome data does not" in result.differences[0]


def test_a_field_only_they_sent_is_named_in_the_diff() -> None:
    """Diff must be readable by a human deciding under time pressure."""
    theirs = _summary()
    theirs["sha256"] = "0" * 64
    theirs["outcome"]["sub_games"][0]["extra_field"] = "value"
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert any("missing on our side" in difference for difference in result.differences)


def test_a_field_only_we_have_is_named_in_the_diff() -> None:
    theirs = _summary()
    theirs["sha256"] = "0" * 64
    del theirs["outcome"]["sub_games"][0]["result"]
    result = reconcile(GAME_ID, GAME_UID, GROUPS, SUB_GAMES, theirs)
    assert any("missing on their side" in difference for difference in result.differences)
