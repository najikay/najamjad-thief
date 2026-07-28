"""The thief's endgame (T-1514, T-1516, T-1519, T-1526).

Surviving to the horizon and surviving past it score identically, so the last
few steps are a different game from the first thirty. Early on, distance is
worth taking risks for; with two steps left, a move that is safe *this turn* is
worth more than one that is better positioned for a future that will not arrive.

The failure this guards against is specific and was visible in the six-game
rehearsal: a thief that keeps optimising position walks into a corridor on step
34 and loses a game it had already won.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.movement import apply_move, legal_moves
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The fields a thief brain reads off a turn."""

    def __init__(self, board, position, belief=None, scent=None, steps_left=None):
        self.board = board
        self.own_position = position
        self.belief = belief or {}
        self.scent = scent or {}
        self.legal = legal_moves(board, position)
        self.role = "thief"
        if steps_left is not None:
            self.steps_remaining = steps_left


def routes(board, cell) -> int:
    """How many moves genuinely change our cell from here."""
    return len(legal_moves(board, cell, mobile_only=True))


# ------------------------------------------------------------------ threshold


def test_the_thief_knows_how_many_steps_are_left():
    """Risk tolerance cannot fall toward the horizon if nothing tracks it."""
    brain = ThiefBrain()
    board = build_state(Role.THIEF).board

    assert brain.steps_remaining(Facts(board, (3, 3), steps_left=2)) == 2


def test_an_absent_countdown_is_treated_as_early_game():
    """Most callers do not supply it; the policy must not change under them."""
    brain = ThiefBrain()
    board = build_state(Role.THIEF).board

    assert brain.steps_remaining(Facts(board, (3, 3))) > brain.stall_trigger


@pytest.mark.parametrize("left,stalling", [(0, True), (1, True), (2, True), (5, False), (30, False)])
def test_stalling_engages_only_near_the_horizon(left, stalling):
    """Switching early would cost the positioning that gets us there."""
    brain = ThiefBrain()
    board = build_state(Role.THIEF).board

    assert brain.is_endgame(Facts(board, (3, 3), steps_left=left)) is stalling


# ------------------------------------------------------------------- behaviour


def test_in_the_endgame_the_thief_prefers_the_safer_cell():
    """With two steps left, room now beats position later."""
    state = build_state(Role.THIEF, position=(3, 3))
    board = state.board
    brain = ThiefBrain()
    facts = Facts(board, (3, 3), belief={(0, 0): 0.9}, steps_left=2)

    chosen = brain.pick_move(facts)
    landing = apply_move(board, (3, 3), chosen)

    assert routes(board, landing) >= 2, "never step into a pocket on the last turns"


def test_at_the_horizon_the_thief_moves_out_of_a_pocket_toward_room():
    """The exact loss this exists to prevent: being cornered on step 34.

    My first version of this test asserted the thief would avoid `(0, 0)`, on
    the assumption it was the dead end. It is not — with barriers at `(0, 2)`
    and `(1, 1)` the *starting* cell has one exit and `(0, 0)` has two. The
    brain was right and the test was wrong, so it now asserts the property that
    actually matters: the endgame move never reduces the room we have.
    """
    state = build_state(Role.THIEF, position=(0, 1))
    board = state.board.with_barrier((0, 2)).with_barrier((1, 1))
    brain = ThiefBrain()

    chosen = brain.pick_move(Facts(board, (0, 1), belief={(6, 6): 0.9}, steps_left=1))
    landing = apply_move(board, (0, 1), chosen)

    assert routes(board, landing) >= routes(board, (0, 1)), "never trade room away at the horizon"
    assert routes(board, landing) == 2


def test_early_game_still_maximises_the_survival_value():
    """Stalling must not leak into the thirty steps before it."""
    state = build_state(Role.THIEF, position=(3, 3))
    brain = ThiefBrain()
    early = Facts(state.board, (3, 3), belief={(0, 0): 0.9}, steps_left=30)

    assert brain.is_endgame(early) is False
    assert brain.pick_move(early) in early.legal


def test_the_trigger_is_configurable():
    """The sweep varies it; a constant would report a flat line."""
    assert ThiefBrain(stall_trigger=8).stall_trigger == 8


# ------------------------------------------------------- immobilisation (T-1519)


def test_the_thief_keeps_more_than_one_exit_when_it_can():
    """A cell with one exit is one barrier from a capture."""
    state = build_state(Role.THIEF, position=(3, 3))
    brain = ThiefBrain()

    chosen = brain.pick_move(Facts(state.board, (3, 3), belief={(6, 6): 0.5}))
    landing = apply_move(state.board, (3, 3), chosen)

    assert routes(state.board, landing) >= 2


def test_a_thief_with_no_legal_move_stays_rather_than_raising():
    """Zero legal moves is the immobilisation signal, not a crash (T-1526)."""
    state = build_state(Role.THIEF, position=(0, 0))
    facts = Facts(state.board, (0, 0))
    facts.legal = ()

    assert ThiefBrain().pick_move(facts) is Move.STAY


def test_an_all_fresh_scent_field_does_not_paralyse_the_thief():
    """Every cell looking equally betrayed must still yield a legal move."""
    state = build_state(Role.THIEF, position=(3, 3))
    scent = dict.fromkeys(state.board.cells(), 0.9)

    move = ThiefBrain().pick_move(Facts(state.board, (3, 3), scent=scent))

    assert move in legal_moves(state.board, (3, 3))


def test_the_policy_is_deterministic_under_identical_facts():
    """Replay is a graded deliverable."""
    state = build_state(Role.THIEF, position=(3, 3))
    brain = ThiefBrain()
    facts = Facts(state.board, (3, 3), belief={(0, 0): 0.7}, steps_left=2)

    assert brain.pick_move(facts) is brain.pick_move(facts)
