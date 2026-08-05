"""Tests for per-mini-game state: decision facts, snapshots, sealed state string."""

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.game_state import GameState
from tests.fakes.orchestration import build_state


def test_facts_expose_everything_a_brain_may_look_at() -> None:
    state = build_state(Role.COP)
    facts = state.facts((Move.SOUTH, Move.EAST, Move.STAY))
    assert facts.role == "police"
    assert facts.own_position == (0, 0)
    assert facts.legal == (Move.SOUTH, Move.EAST, Move.STAY)
    assert facts.barriers_left == 14
    assert len(facts.belief) == 49
    assert len(facts.scent) == 49


def test_facts_keep_the_two_scent_fields_apart() -> None:
    """They answer different questions and were being conflated.

    `scent` is the opponent's trail, which is what our belief is inferred from.
    `own_scent` is ours, which is what the thief consults to avoid re-treading
    perfumed ground. Only the first existed, so the thief's leak term was
    reading the wrong agent's deposits — and against a peer that emits nothing
    it read a field of zeros.
    """
    state = build_state(Role.THIEF)
    state.own_scent.deposit(state.own_position)

    facts = state.facts((Move.NORTH,))

    assert facts.own_scent[state.own_position] > 0.0
    assert facts.scent[state.own_position] == 0.0


def test_facts_carry_the_last_hint_for_the_speaker() -> None:
    state = build_state(Role.THIEF)
    state.last_opponent_hint = "I can smell you near the bridge"
    assert state.facts(()).last_hint == "I can smell you near the bridge"


def test_barriers_left_tracks_usage() -> None:
    state = build_state(Role.COP)
    state.barriers_used = 5
    assert state.barriers_left == 9


def test_snapshot_is_serialisable_for_crash_resume() -> None:
    """A6 lesson: state we cannot restore is state we lose on a crash."""
    state = build_state(Role.COP)
    state.step = 4
    state.full_turns = 2
    state.board = state.board.with_barrier((1, 1))
    state.barriers_used = 1
    state.last_opponent_hint = "somewhere north"
    snapshot = state.snapshot()
    assert snapshot["sub_game"] == 1
    assert snapshot["role"] == "police"
    assert snapshot["step"] == 4
    assert snapshot["full_turns"] == 2
    assert snapshot["own_position"] == [0, 0]
    assert snapshot["barriers"] == [[1, 1]]
    assert snapshot["barriers_used"] == 1
    assert snapshot["last_opponent_hint"] == "somewhere north"


def test_snapshot_includes_belief_peak_and_scent(state_with_scent: GameState) -> None:
    snapshot = state_with_scent.snapshot()
    assert snapshot["belief_peak"]
    assert snapshot["opponent_scent"]


def test_state_string_describes_the_board_for_the_sealed_record() -> None:
    state = build_state(Role.THIEF)
    assert state.state_string() == "grid=7x7;self=[3, 3];barriers=[]"


def test_state_string_lists_barriers_deterministically() -> None:
    """Both peers hash this string, so ordering must never vary."""
    state = build_state(Role.COP)
    state.board = state.board.with_barrier((2, 2)).with_barrier((1, 1))
    assert state.state_string() == "grid=7x7;self=[0, 0];barriers=[[1, 1], [2, 2]]"
