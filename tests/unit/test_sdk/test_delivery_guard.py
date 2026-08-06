"""A counted match that can only draft its report has not been played.

Rules 33-34 require the JSON to be *sent*. A draft sits in a folder, rule 35
scores an undelivered report as not having played, and nothing about the run
looks wrong because drafting succeeds.

The interesting half is where this must **not** fire. A first version guarded
inside `build_sdk`, which every command calls — so `archive`, `peer`, the
dashboard and `preflight` all raised, with `mode = "draft"` being the committed
default in both repos. It broke the shipped state: six tests red, CI failing on
both sides, and `preflight` — whose whole job is to report that very setting —
dying with a traceback instead of printing its checklist.
"""

import pytest

from najamjad_agent.sdk.actions import AgentActions
from najamjad_agent.shared.practice import PracticeError, guard_counted_delivery


def test_a_counted_run_must_deliver() -> None:
    with pytest.raises(PracticeError, match="must deliver its report"):
        guard_counted_delivery("draft", counted=True)


def test_the_refusal_names_the_rule_and_the_fix() -> None:
    """The operator is minutes from a match and needs the sentence to act on."""
    with pytest.raises(PracticeError) as caught:
        guard_counted_delivery("draft", counted=True)

    message = str(caught.value)
    assert "rule 35" in message
    assert 'email.mode = "send"' in message


def test_sending_and_practice_both_pass() -> None:
    assert guard_counted_delivery("send", counted=True) == "send"
    assert guard_counted_delivery("draft", counted=False) == "draft"


def test_building_an_agent_never_raises() -> None:
    """The regression. Construction is not the act the rule is about."""
    assert AgentActions(email_mode="draft") is not None


def test_a_double_without_an_email_mode_is_left_alone() -> None:
    """Every test fake builds `AgentActions()` with no mode and no intent to mail."""
    actions = AgentActions()

    with pytest.raises(RuntimeError, match="no match configured"):
        actions.play_match()


def test_playing_a_counted_series_in_draft_is_refused() -> None:
    """The one place it should fire: a series is about to be played for real."""
    actions = AgentActions(email_mode="draft")
    actions.attach_match(object())

    with pytest.raises(PracticeError, match="must deliver its report"):
        actions.play_match()
