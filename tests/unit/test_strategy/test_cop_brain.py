"""Tests for the cop's pursuit policy and barrier planning."""


from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.board import Board
from najamjad_agent.strategy.base import escape_routes, expected_distance, move_towards
from najamjad_agent.strategy.cop_brain import CopBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The read-only view a brain is given."""

    def __init__(self, board: Board, position, belief: dict, legal=None, barriers_left: int = 14):
        self.board = board
        self.own_position = position
        self.belief = belief
        self.legal = legal if legal is not None else tuple(Move)
        self.barriers_left = barriers_left
        self.role = "police"
        self.step = 1
        self.sub_game = 1


def _point_belief(cell, mass: float = 1.0) -> dict:
    return {cell: mass}


def test_the_cop_moves_toward_the_believed_thief() -> None:
    state = build_state(Role.COP)
    facts = Facts(state.board, (0, 0), _point_belief((6, 0)))
    assert CopBrain().pick_move(facts) is Move.SOUTH


def test_the_cop_moves_east_when_the_thief_is_east() -> None:
    state = build_state(Role.COP)
    facts = Facts(state.board, (0, 0), _point_belief((0, 6)))
    assert CopBrain().pick_move(facts) is Move.EAST


def test_the_cop_closes_distance_every_turn() -> None:
    """Pursuit must actually converge, not orbit."""
    state = build_state(Role.COP)
    brain = CopBrain()
    position = (0, 0)
    target = (6, 6)
    distances = []
    for _ in range(8):
        facts = Facts(state.board, position, _point_belief(target))
        move = brain.pick_move(facts)
        row, col = state.board.delta_for(move)
        position = (position[0] + row, position[1] + col)
        distances.append(Board.manhattan(position, target))
    assert distances == sorted(distances, reverse=True), "distance never increased"
    assert distances[-1] < distances[0]


def test_the_cop_intercepts_rather_than_trailing() -> None:
    """Lookahead spreads belief, so we cut the corner instead of following."""
    state = build_state(Role.COP)
    facts = Facts(state.board, (3, 0), _point_belief((3, 6)))
    assert CopBrain().pick_move(facts) is Move.EAST


def test_an_empty_belief_still_yields_a_legal_move() -> None:
    state = build_state(Role.COP)
    facts = Facts(state.board, (0, 0), {}, legal=(Move.SOUTH, Move.STAY))
    assert CopBrain().pick_move(facts) in (Move.SOUTH, Move.STAY)


def test_no_legal_move_returns_stay() -> None:
    state = build_state(Role.COP)
    assert CopBrain().pick_move(Facts(state.board, (0, 0), {}, legal=())) is Move.STAY


def test_the_cop_prefers_cornering_when_distance_ties() -> None:
    """Freedom-denial breaks ties, which is what walks us toward corners."""
    state = build_state(Role.COP)
    walled = state.board.with_barrier((0, 2)).with_barrier((1, 1))
    facts = Facts(walled, (1, 0), {(0, 1): 0.9, (5, 5): 0.1})
    move = CopBrain().pick_move(facts)
    assert move in (Move.NORTH, Move.EAST)


def test_expected_distance_uses_the_whole_distribution() -> None:
    """Chasing only the peak can walk away from a larger nearby cluster."""
    belief = {(0, 6): 0.4, (1, 0): 0.3, (2, 0): 0.3}
    assert expected_distance(belief, (1, 0)) < expected_distance(belief, (0, 6))


def test_expected_distance_of_an_empty_belief_is_zero() -> None:
    assert expected_distance({}, (0, 0)) == 0.0


def test_escape_routes_counts_open_neighbours() -> None:
    state = build_state(Role.COP)
    assert escape_routes(state.board, (3, 3)) == 4
    assert escape_routes(state.board, (0, 0)) == 2
    assert escape_routes(state.board.with_barrier((1, 0)), (0, 0)) == 1


def test_move_towards_picks_the_closing_move() -> None:
    state = build_state(Role.COP)
    assert move_towards(state.board, (0, 0), (6, 0), tuple(Move)) is Move.SOUTH


def test_move_towards_with_no_options_stays() -> None:
    state = build_state(Role.COP)
    assert move_towards(state.board, (0, 0), (6, 0), ()) is Move.STAY
