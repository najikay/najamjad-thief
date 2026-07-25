"""Property-based invariants for the belief grid: it must always stay a distribution."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams

BOARD = 7
CONFIG = {
    "board_and_agents": {"grid_size": BOARD, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}
cells = st.tuples(st.integers(0, BOARD - 1), st.integers(0, BOARD - 1))
operations = st.sampled_from(["diffuse", "scent", "exclude", "likelihood"])


def _fresh_board(barriers: list) -> Board:
    return Board(GameParams.from_config(CONFIG), barriers=set(barriers))


def _is_distribution(belief: BeliefGrid) -> bool:
    values = belief.as_dict().values()
    return (
        math.isclose(sum(values), 1.0, abs_tol=1e-6)
        and all(value >= 0.0 for value in values)
        and not any(math.isnan(value) or math.isinf(value) for value in values)
    )


@given(
    barriers=st.lists(cells, max_size=10),
    script=st.lists(operations, min_size=1, max_size=15),
    payload=st.dictionaries(cells, st.floats(0.0, 0.9), max_size=10),
)
@settings(max_examples=200, deadline=None)
def test_any_update_sequence_leaves_a_valid_distribution(barriers, script, payload) -> None:
    """Invariant: belief is a probability distribution after every operation."""
    belief = BeliefGrid(_fresh_board(barriers))
    for operation in script:
        if operation == "diffuse":
            belief.diffuse()
        elif operation == "scent":
            belief.update_scent(payload)
        elif operation == "exclude":
            belief.exclude(tuple(payload))
        else:
            belief.apply_likelihood(payload)
        assert _is_distribution(belief), f"broken after {operation}"


@given(barriers=st.lists(cells, max_size=8), weights=st.dictionaries(cells, st.just(0.0), max_size=49))
@settings(max_examples=100, deadline=None)
def test_degenerate_zero_likelihood_recovers(barriers, weights) -> None:
    """Even a fully contradictory observation must leave a usable belief."""
    belief = BeliefGrid(_fresh_board(barriers))
    belief.apply_likelihood(weights)
    assert _is_distribution(belief)


@given(barriers=st.lists(cells, max_size=8), rounds=st.integers(1, 10))
@settings(max_examples=100, deadline=None)
def test_diffusion_keeps_mass_on_open_cells_only(barriers, rounds) -> None:
    """Mass must never sit on a barrier or off the board, however long we run."""
    board = _fresh_board(barriers)
    belief = BeliefGrid(board)
    for _ in range(rounds):
        belief.diffuse()
    assert all(board.is_open(cell) for cell in belief.as_dict())
    assert _is_distribution(belief)


@given(peak=cells, barriers=st.lists(cells, max_size=6))
@settings(max_examples=100, deadline=None)
def test_scent_peak_is_never_less_likely_than_unscented_cells(peak, barriers) -> None:
    board = _fresh_board([cell for cell in barriers if cell != peak])
    belief = BeliefGrid(board)
    belief.update_scent({peak: 0.9})
    unscented = [cell for cell in belief.as_dict() if cell != peak]
    assert all(belief.probability_at(peak) >= belief.probability_at(cell) for cell in unscented)
