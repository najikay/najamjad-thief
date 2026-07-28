"""Movement invariants that must hold for *every* position and move (T-0513).

The example-based tests cover the positions we thought of. These cover the ones
we did not: hypothesis generates the starting cell, the barrier layout and the
whole move sequence, and asserts the properties that make a game legal at all.

Three invariants, and each one is a rule the opponent audits us against:

* an agent is always inside the board;
* an agent never occupies a barrier — impassable means impassable, and it is
  impassable for the cop who placed it too;
* a legal move applied to a legal position yields a legal position, so a long
  sequence cannot drift somewhere a single step could not reach.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.movement import IllegalMoveError, apply_move, legal_moves
from tests.fakes.orchestration import build_state

BOARD = build_state(Role.COP).board
SIZE = BOARD.size
cells = st.tuples(st.integers(0, SIZE - 1), st.integers(0, SIZE - 1))
moves = st.sampled_from(list(Move))
sequences = st.lists(moves, min_size=1, max_size=40)


def walk(board, start, sequence):
    """Apply a sequence, skipping steps the rules refuse."""
    position = start
    for move in sequence:
        if move in legal_moves(board, position):
            position = apply_move(board, position, move)
    return position


@given(start=cells, sequence=sequences)
@settings(max_examples=200, deadline=None)
def test_an_agent_never_leaves_the_board(start, sequence):
    """The most basic legality, over any path."""
    end = walk(BOARD, start, sequence)

    assert 0 <= end[0] < SIZE and 0 <= end[1] < SIZE


@given(start=cells, walls=st.lists(cells, max_size=14), sequence=sequences)
@settings(max_examples=200, deadline=None)
def test_an_agent_never_stands_on_a_barrier(start, walls, sequence):
    """Impassable means impassable — including for the cop who placed it."""
    board = BOARD
    for wall in walls:
        if wall != start:
            board = board.with_barrier(wall)

    end = walk(board, start, sequence)

    assert board.is_open(end), f"ended on a barrier at {end}"


@given(start=cells, walls=st.lists(cells, max_size=10))
@settings(max_examples=200, deadline=None)
def test_every_legal_move_lands_somewhere_legal(start, walls):
    """A single step is the induction base for any sequence."""
    board = BOARD
    for wall in walls:
        if wall != start:
            board = board.with_barrier(wall)

    for move in legal_moves(board, start):
        landing = apply_move(board, start, move)
        assert board.is_open(landing)
        assert 0 <= landing[0] < SIZE and 0 <= landing[1] < SIZE


@given(start=cells, walls=st.lists(cells, max_size=10))
@settings(max_examples=100, deadline=None)
def test_an_illegal_move_raises_rather_than_moving_us(start, walls):
    """Silently clamping would let a peer's bad move become our bad position."""
    board = BOARD
    for wall in walls:
        if wall != start:
            board = board.with_barrier(wall)

    for move in set(Move) - set(legal_moves(board, start)):
        with pytest.raises(IllegalMoveError):
            apply_move(board, start, move)


@given(start=cells)
@settings(max_examples=100, deadline=None)
def test_staying_put_is_always_available(start):
    """`STAY` is never blocked — an agent with no other option must still be
    able to take a turn, and immobilisation is decided by the *mobile* moves
    (book rule 47)."""
    assert Move.STAY in legal_moves(BOARD, start)


@given(start=cells, walls=st.lists(cells, min_size=1, max_size=20))
@settings(max_examples=150, deadline=None)
def test_walling_a_cell_never_widens_the_options(start, walls):
    """Adding a barrier can only remove moves. A layout that gained one would
    mean the board disagreed with itself about what is passable."""
    board = BOARD
    before = set(legal_moves(board, start))
    for wall in walls:
        if wall != start:
            board = board.with_barrier(wall)

    assert set(legal_moves(board, start)) <= before


@given(start=cells, sequence=sequences)
@settings(max_examples=100, deadline=None)
def test_the_same_sequence_always_ends_in_the_same_cell(start, sequence):
    """Replay is a graded deliverable; movement must be a pure function."""
    assert walk(BOARD, start, sequence) == walk(BOARD, start, sequence)
