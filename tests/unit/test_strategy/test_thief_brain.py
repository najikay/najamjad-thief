"""Tests for the thief's evasion policy — survival, not merely distance."""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The read-only view a brain is given."""

    def __init__(self, board: Board, position, belief: dict, scent=None, legal=None):
        self.board = board
        self.own_position = position
        self.belief = belief
        self.scent = scent or {}
        self.legal = legal if legal is not None else tuple(Move)
        self.barriers_left = 0
        self.role = "thief"
        self.step = 1
        self.sub_game = 1


def _board() -> Board:
    return build_state(Role.THIEF).board


def test_the_thief_moves_away_from_the_believed_cop() -> None:
    board = _board()
    facts = Facts(board, (3, 3), {(6, 3): 1.0})
    move = ThiefBrain().pick_move(facts)
    row, col = board.delta_for(move)
    assert Board.manhattan((3 + row, 3 + col), (6, 3)) > Board.manhattan((3, 3), (6, 3))


def test_the_thief_keeps_its_distance_over_several_turns() -> None:
    board = _board()
    brain = ThiefBrain()
    position = (3, 3)
    cop = (6, 3)
    for _ in range(4):
        move = brain.pick_move(Facts(board, position, {cop: 1.0}))
        row, col = board.delta_for(move)
        position = (position[0] + row, position[1] + col)
    assert Board.manhattan(position, cop) >= Board.manhattan((3, 3), cop)


def test_a_thief_never_places_a_barrier() -> None:
    """Barriers are the cop's asymmetric power (book Ch. 3)."""
    assert ThiefBrain().pick_barrier(Facts(_board(), (3, 3), {})) is None


def test_no_legal_move_returns_stay() -> None:
    assert ThiefBrain().pick_move(Facts(_board(), (3, 3), {}, legal=())) is Move.STAY


def test_the_thief_refuses_a_dead_end_that_maximises_distance() -> None:
    """The whole point: the furthest move is often the one that kills you.

    (0,0) is further from the cop but has a single exit; a barrier there ends
    the game. (1,1) keeps room.
    """
    board = _board().with_barrier((0, 1))
    facts = Facts(board, (1, 0), {(6, 6): 1.0}, legal=(Move.NORTH, Move.SOUTH, Move.EAST))
    assert ThiefBrain().pick_move(facts) is not Move.NORTH


def test_the_thief_prefers_open_ground_when_distance_ties() -> None:
    board = _board()
    facts = Facts(board, (3, 3), {(3, 3): 0.0}, legal=(Move.NORTH, Move.STAY))
    assert ThiefBrain().pick_move(facts) in (Move.NORTH, Move.STAY)


def test_the_thief_avoids_its_own_fresh_scent_when_options_otherwise_tie() -> None:
    """We cannot fake a trail, but we need not re-walk one we already laid.

    The cop sits at (0,6), which makes NORTH and EAST identical on distance,
    room and lookahead — so the only thing left to choose on is our own scent.
    Scent is a tie-breaker, not an override: distance still matters more.
    """
    board = _board()
    scent = {(2, 3): 0.9, (3, 4): 0.0}
    facts = Facts(board, (3, 3), {(0, 6): 1.0}, scent=scent, legal=(Move.NORTH, Move.EAST))
    assert ThiefBrain().pick_move(facts) is Move.EAST


def test_distance_still_outranks_scent_avoidance() -> None:
    """Leaking a trail is bad; being caught is worse.

    Cop at (6,5): NORTH gains distance 6 while EAST gains only 4, so the
    genuine safety difference must outweigh the scent we would re-walk.
    """
    board = _board()
    scent = {(2, 3): 0.9}
    facts = Facts(board, (3, 3), {(6, 5): 1.0}, scent=scent, legal=(Move.NORTH, Move.EAST))
    assert ThiefBrain().pick_move(facts) is Move.NORTH


def test_a_newly_declared_barrier_changes_the_plan_immediately() -> None:
    """Cop barrier declarations are truthful and public (rules 15-16)."""
    board = _board()
    brain = ThiefBrain()
    facts = Facts(board, (1, 1), {(6, 6): 1.0}, legal=(Move.NORTH, Move.WEST))
    before = brain.pick_move(facts)

    walled = board.with_barrier((0, 0)).with_barrier((0, 2))
    after = brain.pick_move(Facts(walled, (1, 1), {(6, 6): 1.0}, legal=(Move.NORTH, Move.WEST)))
    assert isinstance(before, Move) and isinstance(after, Move)
    assert after in (Move.NORTH, Move.WEST)


def test_decisions_are_deterministic() -> None:
    """Reproducibility matters for replay and for debugging a lost game."""
    board = _board()
    facts = Facts(board, (3, 3), {(6, 3): 1.0})
    first = ThiefBrain().pick_move(facts)
    assert all(ThiefBrain().pick_move(facts) is first for _ in range(5))


def test_an_empty_belief_still_yields_a_legal_move() -> None:
    board = _board()
    move = ThiefBrain().pick_move(Facts(board, (3, 3), {}, legal=(Move.NORTH, Move.STAY)))
    assert move in (Move.NORTH, Move.STAY)


def test_an_illegal_landing_is_valued_as_impossible() -> None:
    """Defence in depth: the orchestrator filters, but the brain agrees."""
    board = _board()
    facts = Facts(board, (0, 0), {(6, 6): 1.0}, legal=(Move.NORTH, Move.SOUTH))
    assert ThiefBrain().pick_move(facts) is Move.SOUTH


def test_the_lookahead_prefers_room_over_a_one_step_gain() -> None:
    """A move that is safe now and lost next turn must not win."""
    board = _board()
    for cell in [(0, 2), (1, 2), (2, 2)]:
        board = board.with_barrier(cell)
    facts = Facts(board, (1, 1), {(4, 1): 1.0}, legal=(Move.NORTH, Move.WEST, Move.EAST))
    assert ThiefBrain().pick_move(facts) is not Move.EAST


def test_the_brain_can_take_its_board_from_a_supplier() -> None:
    board = _board()
    brain = ThiefBrain(board_supplier=lambda: board)
    facts = Facts(board, (3, 3), {(6, 3): 1.0})
    facts.board = None
    assert brain.pick_move(facts) in tuple(Move)


@pytest.mark.parametrize("cop_cell", [(0, 0), (0, 6), (6, 0), (6, 6), (3, 3)])
def test_the_thief_survives_a_scripted_chase_from_any_corner(cop_cell) -> None:
    """A crude but honest end-to-end check: greedy cop vs our thief."""
    board = _board()
    brain = ThiefBrain()
    thief = (3, 3) if cop_cell != (3, 3) else (0, 0)
    cop = cop_cell
    for _ in range(20):
        move = brain.pick_move(Facts(board, thief, {cop: 1.0}))
        row, col = board.delta_for(move)
        candidate = (thief[0] + row, thief[1] + col)
        thief = candidate if board.is_open(candidate) else thief
        if cop == thief:
            pytest.fail("the thief was caught by a greedy pursuer")
        step_row = (thief[0] > cop[0]) - (thief[0] < cop[0])
        step_col = (thief[1] > cop[1]) - (thief[1] < cop[1])
        cop = (cop[0] + step_row, cop[1]) if step_row else (cop[0], cop[1] + step_col)
    assert cop != thief
