"""Tests for the end-of-game rules, separate from conducting the turn loop."""

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.endings import opponent_end_reason, own_barrier_capture
from tests.fakes.orchestration import build_state


def test_a_barrier_dropped_on_the_believed_thief_captures() -> None:
    """Book rule 46: the barrier itself ends the game."""
    state = build_state(Role.COP)
    state.opponent_estimate = (0, 1)
    assert own_barrier_capture(state, (0, 1)) is EndReason.CAPTURE


def test_a_barrier_placed_elsewhere_does_not_capture() -> None:
    state = build_state(Role.COP)
    state.opponent_estimate = (5, 5)
    assert own_barrier_capture(state, (0, 1)) is None


def test_no_barrier_means_no_barrier_capture() -> None:
    state = build_state(Role.COP)
    state.opponent_estimate = (0, 1)
    assert own_barrier_capture(state, None) is None


def test_a_thief_cannot_capture_by_barrier() -> None:
    """Barriers are the cop's asymmetric power (book Ch. 3)."""
    state = build_state(Role.THIEF)
    state.opponent_estimate = (3, 4)
    assert own_barrier_capture(state, (3, 4)) is None


def test_the_cop_wins_when_the_believed_thief_is_walled_in() -> None:
    """Book rule 47: a thief with no move that changes its cell is captured."""
    state = build_state(Role.COP, position=(6, 6))
    state.board = state.board.with_barrier((1, 0)).with_barrier((0, 1))
    state.opponent_estimate = (0, 0)

    # Deferred, not returned: only we can see this ending, so it is announced
    # on one final sealed turn. Closing here left the opponent timing out and
    # filing a contradictory report (rules 33-35).
    assert opponent_end_reason(state, {}) is None
    assert state.pending_end is EndReason.CAPTURE


def test_an_unconfined_thief_is_not_captured() -> None:
    state = build_state(Role.COP, position=(6, 6))
    state.opponent_estimate = (3, 3)
    assert opponent_end_reason(state, {}) is None


def test_the_survival_clock_ends_the_game() -> None:
    state = build_state(Role.COP, position=(6, 6))
    state.opponent_estimate = (3, 3)
    state.full_turns = 35

    assert opponent_end_reason(state, {}) is None
    assert state.pending_end is EndReason.SURVIVAL


def test_a_capture_claim_naming_our_cell_ends_it_for_the_thief() -> None:
    state = build_state(Role.THIEF, position=(3, 3))
    state.claimed_cell = (3, 3)

    # The thief owes an honest answer first (rules 21-22).
    assert opponent_end_reason(state, {"capture_claim": True}) is None
    assert state.pending_end is EndReason.CAPTURE


def test_a_capture_claim_naming_another_cell_is_answered_honestly() -> None:
    """Rules 21-22: we answer from our true cell, so a wrong claim simply fails."""
    state = build_state(Role.THIEF, position=(3, 3))
    state.claimed_cell = (0, 0)
    assert opponent_end_reason(state, {"capture_claim": True}) is None


def test_a_claim_without_a_named_cell_cannot_land() -> None:
    state = build_state(Role.THIEF, position=(3, 3))
    state.claimed_cell = None
    assert opponent_end_reason(state, {"capture_claim": True}) is None


def test_a_declared_win_closes_the_game_on_our_side() -> None:
    """The opponent's announcement is how we learn about an ending only they
    could see. Without it we wait out the deadline and file a timeout for a
    game they have already recorded as survival."""
    state = build_state(Role.COP, position=(6, 6))

    assert opponent_end_reason(state, {"win_claim": "survival"}) is EndReason.SURVIVAL


def test_an_answered_capture_claim_closes_the_game_for_the_cop() -> None:
    state = build_state(Role.COP, position=(3, 3))

    assert opponent_end_reason(state, {"claim_response": True}) is EndReason.CAPTURE


def test_a_denied_capture_claim_does_not_end_anything() -> None:
    state = build_state(Role.COP, position=(3, 3))

    assert opponent_end_reason(state, {"claim_response": False}) is None
    assert state.pending_end is None


def test_a_nonsense_win_claim_is_ignored_rather_than_trusted() -> None:
    """A peer cannot end a game by inventing a reason."""
    state = build_state(Role.COP, position=(6, 6))

    assert opponent_end_reason(state, {"win_claim": "i_just_win"}) is None
