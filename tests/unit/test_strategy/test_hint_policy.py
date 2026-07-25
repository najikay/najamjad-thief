"""Tests for the deception budget — when to lie, and when a lie is wasted."""

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.hint_evidence import HintClaim
from najamjad_agent.strategy.hint_policy import HintPolicy


@pytest.fixture()
def policy() -> HintPolicy:
    return HintPolicy(max_lies=6)


def test_opening_turns_tell_the_truth_to_build_credit(policy: HintPolicy) -> None:
    """Truths are cheap early — the opponent has little belief to spoil."""
    assert policy.choose_intent(step=1, max_steps=35, opponent_trust=0.8, pressure=0.1) == "truth"


def test_a_high_pressure_moment_spends_a_lie(policy: HintPolicy) -> None:
    """A believed lie when the cop is closing is worth several turns of running."""
    assert policy.choose_intent(step=20, max_steps=35, opponent_trust=0.8, pressure=0.9) == "lie"


def test_a_quiet_late_turn_still_tells_the_truth(policy: HintPolicy) -> None:
    assert policy.choose_intent(step=20, max_steps=35, opponent_trust=0.8, pressure=0.2) == "truth"


def test_an_early_emergency_overrides_the_opening_rule(policy: HintPolicy) -> None:
    """Being nearly caught on step 2 is not a moment for honesty."""
    assert policy.choose_intent(step=2, max_steps=35, opponent_trust=0.9, pressure=0.95) == "lie"


def test_no_lies_are_told_once_the_budget_is_spent() -> None:
    policy = HintPolicy(max_lies=1)
    assert policy.choose_intent(10, 35, 0.9, pressure=0.9) == "lie"
    policy.record("lie")
    assert policy.budget_left == 0
    assert policy.choose_intent(11, 35, 0.9, pressure=0.9) == "truth"


def test_a_distrusted_speaker_stops_lying(policy: HintPolicy) -> None:
    """If they no longer believe us, a lie is wasted breath; truth rebuilds."""
    assert policy.choose_intent(20, 35, opponent_trust=0.1, pressure=0.9) == "truth"


def test_pressure_rises_as_the_cop_closes(policy: HintPolicy) -> None:
    far = policy.pressure_for_thief(distance_to_cop=6, steps_survived=2, threshold=35)
    near = policy.pressure_for_thief(distance_to_cop=1, steps_survived=2, threshold=35)
    assert near > far


def test_pressure_rises_near_the_survival_threshold(policy: HintPolicy) -> None:
    """A nearly-won game is exactly when a lie is worth spending."""
    early = policy.pressure_for_thief(distance_to_cop=6, steps_survived=2, threshold=35)
    late = policy.pressure_for_thief(distance_to_cop=6, steps_survived=33, threshold=35)
    assert late > early


def test_pressure_is_bounded(policy: HintPolicy) -> None:
    assert 0.0 <= policy.pressure_for_thief(0, 40, 35) <= 1.0


def test_a_lie_our_own_scent_refutes_is_rejected(policy: HintPolicy) -> None:
    """Worse than a truth: it costs credibility and buys nothing (PAGE 46)."""
    claim = HintClaim(direction=Move.NORTH)
    scent = {(5, 3): 0.81, (5, 4): 0.62}
    assert not policy.plausible(claim, scent, own_position=(3, 3))


def test_a_lie_the_scent_supports_is_allowed(policy: HintPolicy) -> None:
    claim = HintClaim(direction=Move.NORTH)
    scent = {(1, 3): 0.81, (2, 3): 0.62}
    assert policy.plausible(claim, scent, own_position=(3, 3))


def test_an_unverifiable_claim_counts_as_plausible(policy: HintPolicy) -> None:
    """With no scent evidence either way, the lie is safe to tell."""
    assert policy.plausible(HintClaim(direction=Move.NORTH), {}, own_position=(3, 3))


def test_a_misdirection_avoids_our_actual_direction(policy: HintPolicy) -> None:
    chosen = policy.choose_lie_direction(
        legal=(Move.NORTH, Move.SOUTH, Move.EAST, Move.STAY),
        actual=Move.NORTH,
        own_scent={},
        own_position=(3, 3),
    )
    assert chosen is not Move.NORTH
    assert chosen is not Move.STAY


def test_a_misdirection_our_scent_refutes_is_skipped(policy: HintPolicy) -> None:
    """The trail we already laid rules some lies out entirely."""
    scent = {(5, 3): 0.81}
    chosen = policy.choose_lie_direction(
        legal=(Move.NORTH, Move.EAST),
        actual=Move.EAST,
        own_scent=scent,
        own_position=(3, 3),
    )
    assert chosen is not Move.NORTH


def test_no_plausible_lie_returns_none(policy: HintPolicy) -> None:
    """An edge case with a real answer: say something true instead."""
    assert policy.choose_lie_direction((Move.NORTH, Move.STAY), Move.NORTH, {}, (3, 3)) is None


def test_recording_tracks_the_budget_and_catches(policy: HintPolicy) -> None:
    policy.record("lie", believed=True)
    policy.record("lie", believed=False)
    policy.record("truth")
    assert policy.lies_told == 2
    assert policy.lies_caught == 1
    assert len(policy.history) == 3


def test_the_budget_resets_between_mini_games(policy: HintPolicy) -> None:
    """Budgets are per game; the opponent's memory of us is not."""
    policy.record("lie")
    policy.reset_for_new_game()
    assert policy.budget_left == 6
    assert policy.history == []
