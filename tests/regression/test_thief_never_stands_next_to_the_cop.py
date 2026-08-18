"""Adjacency loses this turn; a wall-trap loses in two (T-2717).

Our thief lost a self-play game on 2026-08-18 by playing `STAY` at (0,1) with
the cop on (1,1) and two open escapes. The cause was a *ranking* inversion, not
a missing test: `survives_one_wall` rejected both escapes — (0,0) and (0,2) sit
in a corner where one barrier forces a capture — and passed the adjacent STAY,
because standing beside a cop is not a forced win in the solver's sense. The
thief can step away next turn. It just has to actually do it.

But the cop moves after us, so a thief that *ends its move* adjacent is taken by
a cop that simply steps forward. The two deaths are a turn count apart: the
wall-trap costs the cop a turn to build and then still has to close, and may
never happen at all. Later strictly dominates now.
"""

import json

from najamjad_agent.constants import Move
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams
from najamjad_agent.strategy.wall_safety import safe_landings, survives_one_wall

WALLS = ((0, 3), (1, 3), (2, 3), (3, 3))
COP, THIEF = (1, 1), (0, 1)


def board() -> Board:
    with open("config/game.json") as handle:
        grid = Board(GameParams.from_config(json.load(handle)))
    for wall in WALLS:
        grid = grid.with_barrier(wall)
    return grid


def test_the_oracle_really_does_pass_the_fatal_move() -> None:
    """The premise of the bug, pinned so the fix is not mistaken for the cause."""
    grid = board()

    assert survives_one_wall(grid, COP, THIEF, 10) is True, "staying looks 'safe'"
    assert survives_one_wall(grid, COP, (0, 0), 10) is False
    assert survives_one_wall(grid, COP, (0, 2), 10) is False


def test_the_escapes_are_preferred_over_the_wall_safe_death() -> None:
    """The fix: leave, even though leaving is what the wall oracle rejects."""
    landings = safe_landings(board(), COP, THIEF, 10, ((0, 1), (0, 0), (0, 2)))

    assert (0, 1) not in landings, "never end the move beside the cop"
    assert set(landings) == {(0, 0), (0, 2)}


def test_a_clear_and_wall_safe_landing_still_outranks_a_merely_clear_one() -> None:
    """The precedence is four-deep, and the top of it must not have been lost."""
    grid = board()
    # (3,1) is two from the cop *and* wall-safe; (0,0) and (0,2) are clear but
    # the oracle rejects both, and (0,1) is the wall-safe death. Note (2,1) does
    # not belong here however safe it looks — it is directly below the cop, so
    # it is adjacent, and that is the whole point of the tier above.
    moves = ((0, 1), (0, 0), (0, 2), (3, 1))

    landings = safe_landings(grid, COP, THIEF, 10, moves)

    assert landings == ((3, 1),), "the one that is both clear and wall-safe"


def test_a_pocket_where_everything_is_adjacent_still_returns_something() -> None:
    """The fallback that keeps the caller out of its blind policy.

    In a closed pocket every legal landing may touch the cop. Returning nothing
    there would drop `ThiefBrain` into the weighted-move fallback at the exact
    moment it most needs the ranking it already has.
    """
    landings = safe_landings(board(), COP, THIEF, 10, ((0, 1), (1, 0), (2, 1)))

    assert landings, "never empty while a legal move exists"


def test_the_thief_does_not_play_stay_from_the_losing_cell() -> None:
    """End to end, through the brain that actually decides."""
    from najamjad_agent.constants import Role
    from najamjad_agent.domain.belief import BeliefGrid
    from najamjad_agent.domain.game_state import GameState
    from najamjad_agent.domain.ledger import CommitLedger
    from najamjad_agent.domain.scent import ScentField
    from najamjad_agent.strategy.thief_brain import ThiefBrain
    from tests.regression.cop_duel import Facts

    grid = board()
    state = GameState(
        board=grid, role=Role.THIEF, sub_game=1, own_position=THIEF,
        belief=BeliefGrid(grid, start=COP), own_scent=ScentField(board_size=grid.size),
        opponent_scent=ScentField(board_size=grid.size), ledger=CommitLedger(sub_game=1),
    )
    # A point mass on the cop, which is what a read scent frame converges to and
    # exactly the certainty the thief held on the turn it threw the game.
    belief = dict.fromkeys(grid.cells(), 0.0)
    belief[COP] = 1.0
    facts = Facts(state, belief, 0)
    facts.own_position = THIEF
    facts.cop_position = COP
    facts.legal = (Move.STAY, Move.WEST, Move.EAST)

    assert ThiefBrain().pick_move(facts) is not Move.STAY
