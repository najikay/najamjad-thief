"""The thief's survival invariant — the rule that replaced a lost weighted sum.

The claim under test is strong and worth stating: one cop cannot catch a
careful thief on an open grid. A 7x7 board is a product of two paths, and the
cop number of a product of two trees is 2 (Maamoun and Meyniel), so a lone
pursuer is evadable. These tests pin the discipline that cashes that in.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy import thief_safety
from najamjad_agent.strategy.territory import distances_from
from tests.fakes.orchestration import build_state

ALL_MOVES = tuple(Move)


@pytest.fixture()
def board() -> Board:
    return build_state(Role.THIEF).board


def landing(board: Board, origin, move: Move):
    row, col = board.delta_for(move)
    return (origin[0] + row, origin[1] + col)


def test_no_chosen_move_ends_within_reach_of_the_cop(board: Board) -> None:
    """The whole invariant: at distance two the cop cannot take us next turn."""
    origin, cop = (3, 3), (3, 5)

    for move in thief_safety.choose(board, origin, cop, ALL_MOVES):
        reached = distances_from(board, cop).get(landing(board, origin, move))
        assert reached >= thief_safety.SAFE_DISTANCE


def test_an_adjacent_cop_is_stepped_away_from(board: Board) -> None:
    """Distance one is the emergency; the rule must restore distance two."""
    origin, cop = (3, 3), (3, 4)

    for move in thief_safety.choose(board, origin, cop, ALL_MOVES):
        assert distances_from(board, cop).get(landing(board, origin, move), 0) >= 2


def test_a_cornered_thief_still_escapes(board: Board) -> None:
    """A corner is survivable, which is exactly what the old policy denied.

    Cornered at [0,6] with the cop at [0,5], stepping to [1,6] restores
    distance two; the cop follows and we step back. The oscillation never loses,
    and believing otherwise is what made the old brain flee corners into worse
    ones.
    """
    chosen = thief_safety.choose(board, (0, 6), (0, 5), ALL_MOVES)

    assert Move.STAY not in chosen
    for move in chosen:
        assert distances_from(board, (0, 5)).get(landing(board, (0, 6), move), 0) >= 2


def test_room_outranks_distance(board: Board) -> None:
    """The correction, stated as a test.

    The old policy scored distance first and room second, and that ordering is
    precisely what walked us into a far corner instead of a near hall. Ranking
    a big room against a distant cramped cell must now prefer the room.
    """
    reach = distances_from(board, (6, 6))
    spacious = thief_safety.rank(board, (3, 3), Move.STAY, reach, frozenset())
    assert spacious[1] > 0, "component size is the second key and must be populated"

    walled = Board(board.params, [(0, 1), (1, 0)])
    cramped_key = thief_safety.rank(walled, (0, 0), Move.STAY, distances_from(walled, (6, 6)),
                                    frozenset())
    assert cramped_key[1] < spacious[1], "a sealed pocket must rank below open board"


def test_a_cut_cell_is_avoided_while_the_cop_can_still_wall(board: Board) -> None:
    """Standing beyond an articulation point invites the barrier that seals it."""
    reach = distances_from(board, (6, 6))
    exposed = thief_safety.rank(board, (3, 3), Move.STAY, reach, frozenset({(3, 4)}))
    clear = thief_safety.rank(board, (3, 3), Move.STAY, reach, frozenset())

    assert exposed < clear


def test_the_fallback_is_graded_and_never_offers_the_cop_s_own_cell(board: Board) -> None:
    """Distance 1 is survivable; distance 0 is a loss. They must not be pooled.

    The first version fell straight back to every legal move once nothing was
    safe, so the ranking was free to pick the cop's own cell — and did, walking
    into a capture on step 34 of a game otherwise won.
    """
    offered = thief_safety.safe_moves(board, (3, 3), (3, 3), ALL_MOVES)

    assert Move.STAY not in offered, "staying on the cop's cell is never a move"
    for move in offered:
        assert distances_from(board, (3, 3)).get(landing(board, (3, 3), move), 0) >= 1


def test_the_tied_set_is_returned_so_ties_can_be_broken_safely(board: Board) -> None:
    """Randomising happens over this set, so everything in it must be safe."""
    chosen = thief_safety.choose(board, (3, 3), (6, 6), ALL_MOVES)

    assert len(chosen) >= 1
    for move in chosen:
        assert distances_from(board, (6, 6)).get(landing(board, (3, 3), move), 0) >= 2


def test_a_sealed_pocket_reads_as_cramped(board: Board) -> None:
    """`cramped` is the trap detector the neighbour count fired too late to be."""
    walled = Board(board.params, [(0, 1), (1, 0)])

    assert thief_safety.cramped(walled, (0, 0))
    assert not thief_safety.cramped(board, (3, 3))
