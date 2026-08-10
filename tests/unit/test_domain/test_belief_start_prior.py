"""The opponent's start is a signed term, and we used to throw it away (T-2535).

`BeliefGrid` opened uniform over every open cell while `GameParams` carried
`cop_start` and `thief_start` straight from the agreed `config/game.json` —
byte-identical on both sides and verified by the handshake signature. So at
step 0 we knew exactly where the opponent stood and began by not knowing.

That cost games. Under a flat prior `blind.uninformative` is true on turn one,
so the thief takes the blind policy, which reasons about board geometry rather
than about the opponent — and walks into a cop standing next to it.
"""

from najamjad_agent.constants import Role
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import apply_move, legal_moves
from najamjad_agent.domain.params import GameParams
from najamjad_agent.sdk.state_setup import build_state, opponent_start
from najamjad_agent.strategy.thief_brain import ThiefBrain


def _params(cop=(0, 0), thief=(6, 6)) -> GameParams:
    return GameParams.from_config({
        "board_and_agents": {"grid_size": 7, "cop_start": list(cop), "thief_start": list(thief)},
        "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                                  "max_moves": 35, "survival_threshold": 35},
    })


class _Facts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _first_landing(cop, thief):
    """Where our thief actually steps on turn one, through the real brain."""
    params = _params(cop, thief)
    state = build_state(params, Role.THIEF, 1)
    board = state.board
    brain = ThiefBrain(board_supplier=lambda: board)
    facts = _Facts(legal=legal_moves(board, thief), belief=state.belief.as_dict(),
                   own_position=thief, step=1, sub_game=1, own_scent={}, scent={}, barriers_left=0)
    return apply_move(board, thief, brain.pick_move(facts))


def _adjacent(a, b) -> bool:
    """Manhattan 1 — moves are N/S/E/W, so a diagonal is two steps away."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1


def test_the_prior_is_a_point_mass_on_a_start_we_were_told() -> None:
    """Certainty is correct here: the term is signed, not inferred."""
    board = Board(_params())
    grid = BeliefGrid(board, start=(0, 0))

    assert grid.probability_at((0, 0)) == 1.0
    assert grid.probability_at((3, 3)) == 0.0


def test_without_a_start_it_still_opens_uniform() -> None:
    """Every existing construction must keep the behaviour it had."""
    grid = BeliefGrid(Board(_params()))

    assert 0.0 < grid.probability_at((0, 0)) < 0.05
    assert grid.probability_at((0, 0)) == grid.probability_at((3, 3))


def test_a_start_off_the_board_falls_back_rather_than_emptying_the_grid() -> None:
    """A belief with no mass anywhere cannot be normalised or reasoned over."""
    grid = BeliefGrid(Board(_params()), start=(99, 99))

    assert grid.probability_at((3, 3)) > 0.0


def test_the_opponent_start_is_read_from_our_own_role() -> None:
    """Two repos share this core, so whose cell is whose cannot be a constant."""
    params = _params(cop=(0, 0), thief=(6, 6))

    assert opponent_start(params, Role.THIEF) == (0, 0)
    assert opponent_start(params, Role.COP) == (6, 6)


def test_a_built_mini_game_knows_where_the_cop_is() -> None:
    """The wiring, not the helper — `state_setup` must pass the start through."""
    state = build_state(_params(cop=(2, 5)), Role.THIEF, 1)

    assert state.belief.probability_at((2, 5)) == 1.0
    assert state.belief.peak() == (2, 5)


def test_the_thief_does_not_step_where_the_cop_can_take_it_on_turn_one() -> None:
    """The defect, at the position a live benchmark found it.

    Game 11 of the 2026-08-08 LLM benchmark: cop (6,3), thief (5,4), captured at
    step 1. Reproduced offline against a scripted cop that simply opens toward
    us, so this is our move being wrong rather than the opponent being clever.
    """
    landing = _first_landing((6, 3), (5, 4))

    assert not _adjacent(landing, (6, 3)), f"stepped to {landing}, which the cop can take"


def test_no_adjacent_start_leaves_us_capturable_on_turn_one() -> None:
    """The sweep, because one fixed position proves one fixed position.

    Every legal cop/thief pair one step apart on a 7x7. Measured before the
    seeded prior: 10 of these 168 openings walked into a cell the cop could take
    immediately. After: none.
    """
    doomed = [
        (cop, thief)
        for cop in [(r, c) for r in range(7) for c in range(7)]
        for thief in [(cop[0] + dr, cop[1] + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        if 0 <= thief[0] < 7 and 0 <= thief[1] < 7
        and _adjacent(_first_landing(cop, thief), cop)
    ]

    assert doomed == [], f"{len(doomed)} openings still hand the cop a free capture"
