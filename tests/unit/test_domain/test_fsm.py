"""Tests for the game state machine: legal graph, refusals, and events."""

import pytest

from najamjad_agent.constants import Phase
from najamjad_agent.domain.fsm import (
    TRANSITIONS,
    GameStateMachine,
    IllegalTransitionError,
)

HAPPY_PATH = [
    Phase.WAITING_FOR_OPPONENT,
    Phase.COMPUTING_MOVE,
    Phase.COMMITTING,
    Phase.AWAITING_REVEAL,
    Phase.VERIFYING,
    Phase.WAITING_FOR_OPPONENT,
]


@pytest.fixture()
def fsm() -> GameStateMachine:
    return GameStateMachine(game_uid="uid-1")


def test_game_starts_in_negotiation(fsm: GameStateMachine) -> None:
    assert fsm.phase is Phase.NEGOTIATING
    assert fsm.history == [Phase.NEGOTIATING]


def test_full_turn_cycle_is_legal(fsm: GameStateMachine) -> None:
    for phase in HAPPY_PATH:
        assert fsm.to(phase) is phase
    assert fsm.phase is Phase.WAITING_FOR_OPPONENT


def test_game_end_flows_through_audit_to_reporting(fsm: GameStateMachine) -> None:
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    fsm.to(Phase.GAME_END)
    fsm.to(Phase.AUDITING)
    fsm.to(Phase.REPORTING)
    assert fsm.is_terminal


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (Phase.NEGOTIATING, Phase.COMPUTING_MOVE),
        (Phase.WAITING_FOR_OPPONENT, Phase.COMMITTING),
        (Phase.COMPUTING_MOVE, Phase.VERIFYING),
        (Phase.COMMITTING, Phase.WAITING_FOR_OPPONENT),
        (Phase.AWAITING_REVEAL, Phase.COMMITTING),
        (Phase.VERIFYING, Phase.AUDITING),
        (Phase.GAME_END, Phase.COMPUTING_MOVE),
        (Phase.AUDITING, Phase.WAITING_FOR_OPPONENT),
    ],
)
def test_illegal_transitions_raise_immediately(source: Phase, target: Phase) -> None:
    """Book rule 5: drift must fail loudly at the offending step."""
    fsm = GameStateMachine(phase=source)
    with pytest.raises(IllegalTransitionError, match=f"{source.value} -> {target.value}"):
        fsm.to(target)


def test_illegal_transition_error_names_both_ends() -> None:
    fsm = GameStateMachine(phase=Phase.COMMITTING)
    with pytest.raises(IllegalTransitionError) as caught:
        fsm.to(Phase.GAME_END)
    assert caught.value.source is Phase.COMMITTING
    assert caught.value.target is Phase.GAME_END


def test_reporting_is_terminal() -> None:
    fsm = GameStateMachine(phase=Phase.REPORTING)
    assert fsm.is_terminal
    for phase in Phase:
        assert not fsm.can(phase)


@pytest.mark.parametrize(
    "source",
    [Phase.COMPUTING_MOVE, Phase.AWAITING_REVEAL, Phase.NEGOTIATING, Phase.VERIFYING],
)
def test_technical_loss_is_reachable_from_network_waiting_phases(source: Phase) -> None:
    """Deadline/watchdog must always have somewhere to go (FR-NET-4/5)."""
    fsm = GameStateMachine(phase=source)
    assert fsm.fail("deadline expired") is Phase.TECHNICAL_LOSS


def test_technical_loss_still_reports(fsm: GameStateMachine) -> None:
    """Even a forfeited game must be reported (rule 35)."""
    fsm.fail("watchdog")
    assert fsm.to(Phase.REPORTING) is Phase.REPORTING


def test_audit_failure_leads_to_technical_loss(fsm: GameStateMachine) -> None:
    fsm.to(Phase.WAITING_FOR_OPPONENT)
    fsm.to(Phase.GAME_END)
    fsm.to(Phase.AUDITING)
    assert fsm.fail("TAMPERED") is Phase.TECHNICAL_LOSS


def test_fail_from_a_terminal_state_is_refused() -> None:
    fsm = GameStateMachine(phase=Phase.REPORTING)
    with pytest.raises(IllegalTransitionError):
        fsm.fail("too late")


def test_transitions_emit_correlated_events(fsm: GameStateMachine) -> None:
    events: list[dict] = []
    fsm.on_transition = events.append
    fsm.to(Phase.WAITING_FOR_OPPONENT, step=4)
    assert events == [
        {
            "event": "fsm.transition",
            "game_uid": "uid-1",
            "step": 4,
            "from": "negotiating",
            "to": "waiting_for_opponent",
        }
    ]


def test_failure_events_carry_the_reason(fsm: GameStateMachine) -> None:
    events: list[dict] = []
    fsm.on_transition = events.append
    fsm.fail("response timeout")
    assert events[0]["reason"] == "response timeout"
    assert events[0]["to"] == "technical_loss"


def test_illegal_transition_emits_no_event(fsm: GameStateMachine) -> None:
    events: list[dict] = []
    fsm.on_transition = events.append
    with pytest.raises(IllegalTransitionError):
        fsm.to(Phase.VERIFYING)
    assert events == []


def test_step_is_tracked_across_transitions(fsm: GameStateMachine) -> None:
    fsm.to(Phase.WAITING_FOR_OPPONENT, step=1)
    fsm.to(Phase.COMPUTING_MOVE)
    assert fsm.step == 1
    fsm.to(Phase.COMMITTING, step=2)
    assert fsm.step == 2


def test_every_phase_is_declared_in_the_transition_table() -> None:
    """A new Phase without a table entry would raise KeyError mid-match."""
    assert set(TRANSITIONS) == set(Phase)


def test_no_transition_targets_an_undeclared_phase() -> None:
    for targets in TRANSITIONS.values():
        assert targets <= set(Phase)
