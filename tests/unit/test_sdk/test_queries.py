"""The read models, and the rule they exist to enforce.

Book rules 8-9 make an over-informative dashboard a disqualification, so the
most important test in this file is the one asserting a view model *cannot*
carry the opponent's position, not the ones checking a field is present.
"""

import pytest

from najamjad_agent.constants import Phase, Role
from najamjad_agent.llm.router import LLMRouter
from najamjad_agent.llm.template_provider import TemplateProvider
from najamjad_agent.sdk.queries import (
    assert_local_truth,
    board_view,
    budget_view,
    gatekeeper_view,
    provider_view,
    report_view,
    transcript_view,
    turn_view,
)
from tests.fakes.orchestration import build_state


def test_board_view_exposes_only_what_we_may_draw():
    state = build_state(Role.COP)
    view = board_view(state)

    assert view["own_position"] == list(state.own_position)
    assert view["role"] == Role.COP.value
    assert set(view) == {
        "size", "own_position", "barriers", "belief", "belief_peak",
        "opponent_scent", "role", "step", "barriers_left",
    }


def test_board_view_belief_is_keyed_for_json():
    state = build_state(Role.THIEF)
    view = board_view(state)

    assert all(isinstance(key, str) and "," in key for key in view["belief"])


def test_turn_view_unlocks_only_while_we_compute_a_move():
    state = build_state(Role.COP)

    assert turn_view(state, Phase.COMPUTING_MOVE.value)["locked"] is False
    for phase in (Phase.WAITING_FOR_OPPONENT, Phase.COMMITTING, Phase.AWAITING_REVEAL):
        assert turn_view(state, phase.value)["locked"] is True


def test_turn_view_shows_the_recent_transitions_it_was_given():
    state = build_state(Role.COP)
    history = [Phase.NEGOTIATING, Phase.WAITING_FOR_OPPONENT, Phase.COMPUTING_MOVE]

    view = turn_view(state, Phase.COMPUTING_MOVE.value, history)

    assert view["recent_phases"] == ["negotiating", "waiting_for_opponent", "computing_move"]


def test_turn_view_keeps_only_the_last_eight_transitions():
    state = build_state(Role.COP)
    history = [Phase.COMMITTING, Phase.AWAITING_REVEAL] * 10

    view = turn_view(state, Phase.COMMITTING.value, history)

    assert len(view["recent_phases"]) == 8


def test_transcript_view_keeps_provenance_per_message():
    view = transcript_view([{"direction": "out", "text": "north", "model": "claude-fable-5"}])

    assert view[0]["model"] == "claude-fable-5"
    assert view[0]["intent"] == ""


def test_budget_view_flags_warning_and_degradation():
    class Meter:
        series = type("S", (), {"ratio": 0.75, "should_degrade": False})()

        def report(self):
            return {
                "series_total": 150_000, "series_limit": 200_000, "by_purpose": {"hint": 10},
            }

    view = budget_view(Meter())

    assert view["warning"] is True
    assert view["degraded"] is False
    assert view["series_spent"] == 150_000


def test_budget_view_without_a_meter_says_so_instead_of_guessing():
    assert budget_view(None) == {"available": False}


def test_provider_view_falls_back_to_template_without_a_router():
    assert provider_view(None)["active"] == "template"


def test_provider_view_names_the_model_currently_answering():
    """The badge is how a grader sees which LLM spoke (FR-LLM-2)."""
    router = LLMRouter(providers=[TemplateProvider()])

    view = provider_view(router)

    assert view["active"] == "template"
    assert [entry["provider"] for entry in view["providers"]] == ["template"]


def test_gatekeeper_view_is_sorted_by_service():
    class Keeper:
        def __init__(self, name):
            self.name = name

        def status(self):
            return type("Q", (), {"waiting": 1, "in_flight": 0, "calls_made": 4})()

    view = gatekeeper_view({"gmail": Keeper("gmail"), "anthropic": Keeper("anthropic")})

    assert [row["service"] for row in view] == ["anthropic", "gmail"]


def test_report_view_surfaces_a_send_failure_instead_of_burying_it():
    view = report_view(None, None, error="gmail: insufficient scope")

    assert view["needs_attention"] is True
    assert view["error"] == "gmail: insufficient scope"


def test_report_view_lists_the_differences_behind_a_mismatch():
    class Mismatch:
        status = "mismatch"
        confirmed = False
        differences = ["result.winner: ours=cop theirs=thief"]

    view = report_view(Mismatch(), None)

    assert view["agreement"] is False
    assert view["differences"] == ["result.winner: ours=cop theirs=thief"]


@pytest.mark.parametrize(
    "payload",
    [
        {"opponent_position": [1, 2]},
        {"board": {"their_position": [0, 0]}},
        {"rows": [{"nonce": "deadbeef"}]},
        {"deep": {"list": [{"true_position": [3, 3]}]}},
    ],
)
def test_local_truth_guard_rejects_forbidden_fields_at_any_depth(payload):
    with pytest.raises(ValueError, match="rules 8-9"):
        assert_local_truth(payload)


def test_local_truth_guard_passes_a_legitimate_payload():
    state = build_state(Role.COP)

    assert_local_truth({"board": board_view(state), "transcript": transcript_view([])})
