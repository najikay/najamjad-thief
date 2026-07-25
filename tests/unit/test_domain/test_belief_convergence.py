"""Scenario tests: does the belief engine actually find a moving opponent?

These are the value tests for our league edge — invariants prove the maths is
valid, but only convergence proves it is *useful*. Each scenario scripts a true
opponent path, feeds us only what a peer would legitimately send (their scent
snapshot), and asserts the belief peak locks onto them.
"""

import time

import pytest

from najamjad_agent.constants import Move
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.hint_evidence import HintClaim, claim_likelihood, scent_consistency
from najamjad_agent.domain.params import GameParams
from najamjad_agent.domain.scent import ScentField

STATIONARY = [(5, 5)] * 6
STRAIGHT = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)]
L_SHAPED = [(6, 0), (5, 0), (4, 0), (4, 1), (4, 2), (4, 3)]


def _track(board: Board, path: list, our_cell: tuple = (3, 3)) -> BeliefGrid:
    """Replay an opponent path, updating belief from their scent alone."""
    belief = BeliefGrid(board)
    theirs = ScentField(board_size=board.size)
    ours = ScentField(board_size=board.size)
    for step in path:
        theirs.deposit(step)
        ours.absorb(theirs.snapshot())
        belief.diffuse()
        belief.update_scent({cell: ours.intensity_at(cell) for cell in board.cells()})
        belief.exclude((our_cell,))
        theirs.decay_all()
        ours.decay_all()
    return belief


@pytest.mark.parametrize(
    ("name", "path"),
    [("stationary", STATIONARY), ("straight-line", STRAIGHT), ("l-shaped", L_SHAPED)],
)
def test_belief_peak_locks_onto_the_true_position(board: Board, name: str, path: list) -> None:
    belief = _track(board, path)
    assert Board.manhattan(belief.peak(), path[-1]) <= 1, f"{name}: lost the trail"


def test_belief_concentrates_far_above_the_uniform_prior(board: Board) -> None:
    belief = _track(board, STRAIGHT)
    assert belief.probability_at(STRAIGHT[-1]) > 10 * (1 / 49)


def test_tracking_survives_barriers_on_the_path(board: Board) -> None:
    walled = board.with_barrier((1, 3)).with_barrier((2, 2))
    belief = _track(walled, L_SHAPED)
    assert Board.manhattan(belief.peak(), L_SHAPED[-1]) <= 1


def test_a_lying_hint_does_not_derail_a_locked_belief(board: Board) -> None:
    """The scent has spoken; a contradicting claim must not move the peak away."""
    belief = _track(board, STRAIGHT)
    liar = HintClaim(direction=Move.SOUTH, text="deep in the south end")
    cells = tuple(board.cells())
    belief.apply_likelihood(claim_likelihood(cells, liar, STRAIGHT[-1], credibility=1.0))
    assert Board.manhattan(belief.peak(), STRAIGHT[-1]) <= 1


def _trail_intensities(board: Board, path: list) -> dict:
    field = ScentField(board_size=board.size)
    for step in path:
        field.deposit(step)
        field.decay_all()
    return {cell: field.intensity_at(cell) for cell in board.cells()}


def test_lie_detector_flags_a_claim_against_the_trail(board: Board) -> None:
    """The eastward trail refutes a westward claim, so credibility can be cut."""
    intensities = _trail_intensities(board, STRAIGHT)
    claim = HintClaim(direction=Move.WEST, text="doubling back west")
    assert scent_consistency(claim, intensities, (0, 0)) == "refuted"


def test_lie_detector_confirms_a_claim_matching_the_trail(board: Board) -> None:
    intensities = _trail_intensities(board, STRAIGHT)
    claim = HintClaim(direction=Move.EAST, text="pushing east")
    assert scent_consistency(claim, intensities, (0, 0)) == "consistent"


def test_lie_detector_stays_silent_on_a_perpendicular_claim(board: Board) -> None:
    """An eastward trail says nothing about north/south — do not guess."""
    intensities = _trail_intensities(board, STRAIGHT)
    claim = HintClaim(direction=Move.SOUTH, text="slipping south")
    assert scent_consistency(claim, intensities, (0, 0)) == "unknown"


@pytest.mark.parametrize("size", [7, 15])
def test_full_update_fits_the_move_budget(size: int) -> None:
    """One belief+scent update must stay far under the 5 s move budget."""
    config = {
        "board_and_agents": {"grid_size": size, "thief_start": [3, 3], "cop_start": [0, 0]},
        "movement_and_barriers": {
            "move_set": ["N", "S", "E", "W", "STAY"],
            "max_barriers": 14,
            "max_moves": 35,
            "survival_threshold": 35,
        },
    }
    board = Board(GameParams.from_config(config))
    belief = BeliefGrid(board)
    field = ScentField(board_size=size)
    field.deposit((size // 2, size // 2))
    intensities = {cell: field.intensity_at(cell) for cell in board.cells()}
    start = time.perf_counter()
    belief.diffuse()
    belief.update_scent(intensities)
    belief.exclude(((0, 0),))
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 50, f"{size}x{size} update took {elapsed_ms:.1f} ms"
