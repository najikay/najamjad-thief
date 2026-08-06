"""What survives total silence: the reachability bound and its saturation."""

import pytest

from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy import blind

CONFIG = {
    "board_and_agents": {"grid_size": 7, "thief_start": [3, 3], "cop_start": [0, 0]},
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
}


@pytest.fixture()
def board() -> Board:
    return Board(GameParams.from_config(CONFIG))


def test_the_cop_cannot_be_where_it_has_not_had_time_to_walk(board: Board) -> None:
    """The whole bound in one line: one cell per turn, from an agreed start.

    (6,6) is twelve steps from (0,0), so on step 4 the cop has eight turns of
    travel left before it could stand there. That is not an estimate and does
    not depend on the opponent transmitting anything.
    """
    assert blind.earliest_arrival(board, (6, 6), step=4) == 8


def test_a_cell_the_cop_could_already_occupy_offers_no_warning(board: Board) -> None:
    """Floored at zero: "they could be here" is not negative warning."""
    assert blind.earliest_arrival(board, (1, 1), step=9) == 0
    assert blind.earliest_arrival(board, (0, 0), step=0) == 0


def test_the_bound_goes_vacuous_rather_than_stale(board: Board) -> None:
    """Past the board's diameter it stops claiming anything at all.

    The failure mode this guards is a bound that keeps asserting safety long
    after it has expired, which is how the phantom cop got its authority.
    """
    assert all(blind.earliest_arrival(board, cell, step=13) == 0 for cell in board.cells())


def test_the_warning_bonus_saturates(board: Board) -> None:
    """Two turns of warning is a reaction; a third is a corner.

    The far corner of an empty board offers twelve turns of warning and two
    exits. Paying for all twelve is how a thief talks itself into a coffin, so
    the bonus is capped and room decides from there.
    """
    far = blind.warning_bonus(board, (6, 6), step=0)
    enough = blind.warning_bonus(board, (2, 0), step=0)

    assert far == enough == blind.WARNING_WEIGHT * blind.WARNING_CAP


def test_a_narrow_belief_is_informative_even_when_it_names_no_cell() -> None:
    """The distinction that routing got wrong, pinned.

    Five candidate cells out of forty-nine is far too broad for `_cop_cell` to
    name one and far too sharp to discard. Treating "cannot name a cell" as
    "knows nothing" sent this to the blind policy and cost two self-play games
    at blur 1 — the suite caught it, this keeps it caught.
    """
    narrow = dict.fromkeys([(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)], 0.2)

    assert not blind.uninformative(narrow, open_cells=49)


def test_a_belief_spread_over_the_board_is_not(board: Board) -> None:
    """The genuinely silent case: uniform over every open cell."""
    flat = {cell: 1.0 for cell in board.cells() if board.is_open(cell)}

    assert blind.uninformative(flat, open_cells=49)
    assert blind.uninformative({}, open_cells=49)
    assert blind.uninformative({(0, 0): 0.0, (1, 1): 0.0}, open_cells=49)


def test_support_is_measured_rather_than_peak() -> None:
    """Why the obvious test does not work, stated as an assertion.

    Both of these are perfectly flat over what they cover, so a peak-versus-
    uniform ratio scores them identically at 1.00. Only the support tells them
    apart, which is the whole reason this function counts cells.
    """
    narrow = dict.fromkeys([(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)], 0.2)
    wide = dict.fromkeys([(row, col) for row in range(7) for col in range(7)], 1 / 49)

    assert max(narrow.values()) / sum(narrow.values()) * len(narrow) == pytest.approx(1.0)
    assert max(wide.values()) / sum(wide.values()) * len(wide) == pytest.approx(1.0)
    assert not blind.uninformative(narrow, open_cells=49)
    assert blind.uninformative(wide, open_cells=49)


def test_warning_beats_one_exit_and_not_two() -> None:
    """The weight, stated as the trade it actually makes.

    A provably-safe cell should outbid a neighbour with one more escape route
    and lose to one with two, which is what keeps the bound from overriding the
    room term that survives the bound's expiry.
    """
    assert blind.ROOM_WEIGHT < blind.WARNING_WEIGHT < 2 * blind.ROOM_WEIGHT
