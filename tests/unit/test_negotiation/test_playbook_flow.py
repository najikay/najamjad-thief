"""Tests for the playbook's positions and the negotiation flow's visibility."""

import pytest

from najamjad_agent.negotiation.contract import ContractError
from najamjad_agent.negotiation.flow import Negotiation, NegotiationError, Stage
from najamjad_agent.negotiation.playbook import ACCEPT, COUNTER, REJECT, Playbook

TERMS = {"grid_size": 7, "max_barriers": 14, "max_moves": 35, "survival_threshold": 35}


@pytest.fixture()
def playbook() -> Playbook:
    return Playbook()


@pytest.fixture()
def events() -> list[dict]:
    return []


@pytest.fixture()
def negotiation(events: list[dict]) -> Negotiation:
    return Negotiation(our_group="najamjad", emit=events.append)


def test_every_negotiable_appendix_f_item_has_a_position(playbook: Playbook) -> None:
    """A term with no prepared position is a term we improvise badly at 2am."""
    covered = {position.key for position in playbook.positions}
    assert {
        "grid_size",
        "max_barriers",
        "max_moves",
        "survival_threshold",
        "num_games",
        "hint_max_words",
        "map_area",
        "axis_origin_corner",
        "axis_start_index",
        "response_timeout_sec",
        "watchdog_timeout_sec",
        "token_budget_per_series",
    } <= covered


def test_opening_terms_use_our_preferred_values(playbook: Playbook) -> None:
    opening = playbook.opening_terms()
    # We no longer ask for headroom: a longer turn helps whoever needs time to
    # think, and that is never us. Retries and the send deadline answer a tunnel
    # hiccup without lengthening every turn of the match for both sides.
    assert opening["response_timeout_sec"] == 30, "we ask for the book's own value"
    assert opening["num_games"] == 6


def test_default_terms_are_the_books_own_values(playbook: Playbook) -> None:
    assert playbook.default_terms()["response_timeout_sec"] == 30


def test_an_identical_proposal_is_accepted(playbook: Playbook) -> None:
    assert playbook.evaluate(playbook.opening_terms())["verdict"] == ACCEPT


def test_a_workable_difference_produces_a_counter(playbook: Playbook) -> None:
    """45 s is inside our ceiling, so it is a haggle rather than a refusal."""
    assessment = playbook.evaluate({"response_timeout_sec": 45})
    assert assessment["verdict"] == COUNTER
    assert assessment["counter"]["response_timeout_sec"] == 30
    assert assessment["reasons"], "a counter must explain itself"


def test_lowering_a_minimum_is_rejected_not_countered(playbook: Playbook) -> None:
    """Rule 12 is not a preference, so it is not something we haggle over."""
    assessment = playbook.evaluate({"grid_size": 5})
    assert assessment["verdict"] == REJECT
    assert any("never lowered" in reason for reason in assessment["reasons"])


@pytest.mark.parametrize("red_line", ["numeric_hints", "llm_moves", "skip_audit"])
def test_red_lines_are_rejected_with_a_reason(playbook: Playbook, red_line: str) -> None:
    assessment = playbook.evaluate({red_line: True})
    assert assessment["verdict"] == REJECT
    assert any(red_line in reason for reason in assessment["reasons"])


def test_declining_the_llm_move_exception_is_explained(playbook: Playbook) -> None:
    """We decline on strategy, not dogma — the reason is recorded."""
    reasons = playbook.evaluate({"llm_moves": True})["reasons"]
    assert any("deterministic" in reason for reason in reasons)


def test_unknown_terms_are_ignored_rather_than_refused(playbook: Playbook) -> None:
    """An opponent's private extension is not our business (interop tolerance)."""
    assert playbook.evaluate({"their_custom_flag": 3})["verdict"] == ACCEPT


def test_a_negotiation_starts_idle(negotiation: Negotiation) -> None:
    assert negotiation.stage is Stage.IDLE
    assert negotiation.timeline == []


def test_every_step_is_recorded_on_the_timeline(negotiation: Negotiation) -> None:
    """A6 pain #4: nothing about negotiation may be invisible."""
    negotiation.propose()
    negotiation.receive(negotiation.playbook.opening_terms())
    actions = [entry["action"] for entry in negotiation.timeline]
    assert actions == ["proposed", "accepted"]


def test_steps_are_also_emitted_as_events(negotiation: Negotiation, events: list[dict]) -> None:
    negotiation.propose()
    assert any(event["event"] == "negotiation.proposed" for event in events)


def test_a_full_agreement_reaches_locked(negotiation: Negotiation) -> None:
    from najamjad_agent.negotiation.contract import Contract

    negotiation.propose(TERMS)
    negotiation.agree(TERMS, identity={"group_id": "najamjad"})
    peer = Contract(dict(TERMS), identity={"group_id": "rival"}).signed()
    entry = negotiation.lock(peer, their_group="rival")
    assert negotiation.locked
    assert entry["game_id"] == "najamjad-vs-rival"
    assert len(entry["game_uid"]) == 36
    assert len(entry["sha256"]) == 64


def test_a_mismatched_peer_contract_refuses_and_abandons(negotiation: Negotiation) -> None:
    from najamjad_agent.negotiation.contract import Contract

    negotiation.propose(TERMS)
    negotiation.agree(TERMS)
    peer = Contract({**TERMS, "grid_size": 9}).signed()
    with pytest.raises(ContractError):
        negotiation.lock(peer, their_group="rival")
    assert negotiation.stage is Stage.ABANDONED
    assert negotiation.timeline[-1]["action"] == "refused"


def test_a_red_line_proposal_abandons_the_negotiation(negotiation: Negotiation) -> None:
    negotiation.receive({"llm_moves": True})
    assert negotiation.stage is Stage.ABANDONED
    assert negotiation.timeline[-1]["action"] == "rejected"


def test_locking_before_agreeing_is_refused(negotiation: Negotiation) -> None:
    with pytest.raises(NegotiationError, match="cannot lock before agreeing"):
        negotiation.lock({}, their_group="rival")


def test_a_locked_negotiation_cannot_be_reopened(negotiation: Negotiation) -> None:
    from najamjad_agent.negotiation.contract import Contract

    negotiation.propose(TERMS)
    negotiation.agree(TERMS)
    negotiation.lock(Contract(dict(TERMS)).signed(), their_group="rival")
    with pytest.raises(NegotiationError, match="illegal negotiation step"):
        negotiation.propose(TERMS)


def test_abandoning_is_clean_and_final(negotiation: Negotiation) -> None:
    negotiation.abandon("opponent went quiet")
    assert negotiation.stage is Stage.ABANDONED
    assert negotiation.timeline[-1]["reason"] == "opponent went quiet"
    with pytest.raises(NegotiationError):
        negotiation.propose()


def test_agreeing_from_idle_is_refused(negotiation: Negotiation) -> None:
    with pytest.raises(NegotiationError, match="cannot agree from stage idle"):
        negotiation.agree(TERMS)


def test_a_counter_round_can_lead_to_agreement(negotiation: Negotiation) -> None:
    """The normal path: they propose, we counter, they accept our terms.

    45 s rather than 30 s now, because 30 s *is* our position — a proposal we
    already agree with is accepted, and no counter round happens at all.
    """
    negotiation.receive({"response_timeout_sec": 45})
    assert negotiation.stage is Stage.COUNTERED
    negotiation.agree(TERMS)
    assert negotiation.stage is Stage.AGREED


def test_a_position_without_a_floor_accepts_any_value(playbook: Playbook) -> None:
    """Free-text terms like map_area have no numeric floor to compare."""
    position = playbook.position_for("map_area")
    assert position is not None and position.floor is None
    assert position.acceptable("London")


def test_a_non_numeric_value_for_a_numeric_term_is_refused(playbook: Playbook) -> None:
    """A peer sending 'seven' must not slip past the floor comparison."""
    position = playbook.position_for("grid_size")
    assert position is not None
    assert not position.acceptable("seven")


def test_an_unknown_term_has_no_position(playbook: Playbook) -> None:
    assert playbook.position_for("not_a_real_term") is None
