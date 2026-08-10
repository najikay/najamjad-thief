"""We read the opponent's hints now, and weigh them (T-2536).

The parser, the claim, the likelihood, the lie-detector and the credibility
tracker were all built and tested; `belief.py`'s own docstring described this as
step 3 of the update; and **nothing ever called any of it**. Sixth
finished-but-unreferenced component in this project, and the costliest.

Measured against uoh-ay26, 2026-08-07: a hint on every one of 135 sealed
records, **134/134 direction claims truthful** against their own sealed move,
and zero scent cells — so `update_scent` received nothing and our cop played six
mini-games on diffusion alone while they narrated their position every turn.
"""

from najamjad_agent.constants import Role
from najamjad_agent.domain.params import GameParams
from najamjad_agent.domain.turn_ingress import decay_after_full_turn
from najamjad_agent.sdk.state_setup import build_state

CFG = {
    "board_and_agents": {"grid_size": 7, "cop_start": [0, 0], "thief_start": [6, 6]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                              "max_moves": 35, "survival_threshold": 35},
}
SOUTH_OF_ORIGIN = (1, 0)
EAST_OF_ORIGIN = (0, 1)


def _after(hint: str, credibility: float | None = None, scent: tuple = ()):
    """One full turn with `hint` as the opponent's last word."""
    state = build_state(GameParams.from_config(CFG), Role.THIEF, 1)
    state.opponent_estimate = (0, 0)
    state.last_opponent_hint = hint
    if credibility is not None:
        state.credibility._coefficient = credibility  # noqa: SLF001 - fixing the weight under test
    for cell in scent:
        state.opponent_scent.deposit(cell)
    decay_after_full_turn(state)
    return state


def test_a_direction_claim_moves_belief_that_way() -> None:
    """The whole point: 134 free position fixes a series, previously discarded."""
    state = _after("I moved south.")

    assert state.belief.probability_at(SOUTH_OF_ORIGIN) > state.belief.probability_at(EAST_OF_ORIGIN)


def test_a_hint_that_says_nothing_changes_nothing() -> None:
    """Flavour text must not tilt the grid — most hints are flavour."""
    state = _after("Nice weather today.")

    assert state.belief.probability_at(SOUTH_OF_ORIGIN) == state.belief.probability_at(
        EAST_OF_ORIGIN
    )


def test_silence_changes_nothing() -> None:
    """A peer who sends no hint is not evidence of anything."""
    state = _after("")

    assert state.belief.probability_at(SOUTH_OF_ORIGIN) == state.belief.probability_at(
        EAST_OF_ORIGIN
    )


def test_a_discredited_peer_is_heard_and_disbelieved() -> None:
    """Zero credibility is an identity update, not a mute button.

    This is what "does not trust them blindly" has to mean concretely: we keep
    parsing a known liar's claims — so that a later truthful one can earn weight
    back — while acting on none of it.
    """
    trusted = _after("I moved south.", credibility=1.0)
    ignored = _after("I moved south.", credibility=0.0)

    assert trusted.belief.probability_at(SOUTH_OF_ORIGIN) > ignored.belief.probability_at(
        SOUTH_OF_ORIGIN
    )
    assert ignored.belief.probability_at(SOUTH_OF_ORIGIN) == ignored.belief.probability_at(
        EAST_OF_ORIGIN
    )


def test_belief_still_sums_to_one_after_testimony() -> None:
    """A likelihood is a nudge; it must not leave the grid unnormalised."""
    state = _after("I moved south.")

    assert abs(state.belief.total() - 1.0) < 1e-9


def test_credibility_is_untouched_when_the_trail_cannot_judge_the_claim() -> None:
    """No scent means no cross-examination, so the weight must not drift.

    uoh-ay26 emit no scent at all, so every verdict against them is "unknown".
    Moving trust on an unverifiable claim would let a peer talk their way into
    credibility they never earned — in either direction.
    """
    state = _after("I moved south.")

    assert state.credibility.coefficient == 0.5


def test_the_hint_path_is_reached_from_the_real_turn_update() -> None:
    """The seam. Every assertion above would pass with `_fuse_hint` uncalled.

    That is not a hypothetical failure mode here — it is precisely how this
    component spent the whole project built, tested and unreferenced.
    """
    import inspect

    from najamjad_agent.domain import turn_ingress

    source = inspect.getsource(turn_ingress.decay_after_full_turn)

    assert "_fuse_hint(state)" in source
