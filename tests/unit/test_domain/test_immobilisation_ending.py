"""Rule 47 must end a live game, not just a duel replay.

`capture.evaluate_capture` checked immobilisation, was unit-tested, was used by
the offline duel harness — and had no production caller. So a thief sealed into
a pocket played on as though nothing had happened while the cop scored a
capture, and two peers filing different outcomes for one mini-game is exactly
what rules 33-35 void for both.

`mobile_only` is why an ordinary legal-move check can never catch this: STAY is
never blocked, so a walled-in thief still reports one legal move.
"""

import pytest

from najamjad_agent.constants import EndReason, Role
from najamjad_agent.domain.endings import opponent_end_reason
from najamjad_agent.domain.turn_ingress import absorb_turn
from tests.fakes.orchestration import build_state


@pytest.fixture()
def state():
    return build_state(Role.THIEF)


def _their_turn(state, cell, step):
    """Absorb a declared barrier, then evaluate the ending, in game order."""
    message = {"step": step, "commit": f"{step:064x}", "barrier_placed": list(cell)}
    absorb_turn(state, message, lambda _name, **_fields: None)
    return opponent_end_reason(state, message)


def _seal(state, keep_open=0):
    """Wall the thief in, optionally leaving `keep_open` exits."""
    row, col = state.own_position
    around = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]
    walls = around[: len(around) - keep_open]
    for step, cell in enumerate(walls, start=1):
        _their_turn(state, cell, step)
    return walls


def test_a_thief_with_one_exit_left_plays_on(state) -> None:
    """The instrument must be able to say no, or it is measuring nothing."""
    _seal(state, keep_open=1)

    assert state.pending_end is None


def test_sealing_the_last_exit_ends_the_mini_game(state) -> None:
    """Rule 47: no move but STAY is a capture, and it now closes the game."""
    _seal(state)

    assert state.pending_end is EndReason.CAPTURE


def test_the_concession_names_our_own_cell_not_the_barrier(state) -> None:
    """Rules 18-22 require the answer to be honest, and this one nearly was not.

    The concession travels as an answered capture claim, and the existing code
    named the *barrier's* cell — correct for rule 46, where the wall lands on
    us, and a lie for rule 47, where it takes our last exit without touching
    us. The sealed record would have shown us conceding a capture at a cell we
    did not occupy.
    """
    walls = _seal(state)

    assert state.pending_capture_claim is True
    assert tuple(state.claimed_cell) == tuple(state.own_position)
    assert tuple(state.claimed_cell) not in {tuple(cell) for cell in walls}


def test_a_barrier_dropped_on_us_still_ends_it_the_old_way(state) -> None:
    """Rule 46 is untouched — the check that already worked must keep working."""
    ended = _their_turn(state, state.own_position, step=1)

    assert state.pending_end is EndReason.CAPTURE
    assert ended is None, "the ending is deferred and announced, never closed silently"


def test_the_cop_does_not_conclude_this_from_a_belief(state) -> None:
    """Only the side that knows its own cell may answer.

    A cop concluding immobilisation from `opponent_estimate` is asserting
    something the thief never confirmed, and that is the mistake this codebase
    already removed once. The thief is the honest evaluator here.
    """
    cop = build_state(Role.COP)
    row, col = cop.own_position
    for step, cell in enumerate(
        [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)], start=1
    ):
        if cop.board.in_bounds(cell):
            _their_turn(cop, cell, step)

    assert cop.pending_end is None
