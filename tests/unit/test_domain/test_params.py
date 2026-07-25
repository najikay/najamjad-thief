"""Tests for the agreed game-parameter value object (Appendix F fidelity)."""

import pytest

from najamjad_agent.domain.params import GameParams


def test_from_config_reads_appendix_f_defaults(params: GameParams) -> None:
    assert params.grid_size == 7
    assert params.thief_start == (3, 3)
    assert params.cop_start == (0, 0)
    assert params.max_barriers == 14
    assert params.max_moves == 35
    assert params.survival_threshold == 35


def test_axis_conventions_default_to_top_left_zero(params: GameParams) -> None:
    assert params.axis_origin_corner == "top-left"
    assert params.axis_start_index == 0


def test_grid_size_below_minimum_is_rejected(game_config: dict) -> None:
    """Appendix F Table 13: 7x7 is a binding minimum — never lowerable."""
    game_config["board_and_agents"]["grid_size"] = 6
    with pytest.raises(ValueError, match="grid_size"):
        GameParams.from_config(game_config)


def test_raising_a_minimum_is_allowed(game_config: dict) -> None:
    game_config["board_and_agents"].update(grid_size=10, thief_start=[5, 5])
    game_config["movement_and_barriers"].update(
        max_barriers=20, max_moves=40, survival_threshold=40
    )
    params = GameParams.from_config(game_config)
    assert (params.grid_size, params.max_barriers, params.max_moves) == (10, 20, 40)


@pytest.mark.parametrize(
    ("key", "bad"),
    [("max_barriers", 13), ("max_moves", 34), ("survival_threshold", 34)],
)
def test_lowered_minimums_are_rejected(game_config: dict, key: str, bad: int) -> None:
    game_config["movement_and_barriers"][key] = bad
    with pytest.raises(ValueError, match=key):
        GameParams.from_config(game_config)


def test_altered_move_set_is_rejected(game_config: dict) -> None:
    """Move set is FIXED (Appendix F Table 15): no diagonals may be negotiated in."""
    game_config["movement_and_barriers"]["move_set"] = ["N", "S", "NE"]
    with pytest.raises(ValueError, match="move_set"):
        GameParams.from_config(game_config)


def test_unknown_axis_corner_is_rejected(game_config: dict) -> None:
    game_config["board_and_agents"]["axis_origin_corner"] = "middle"
    with pytest.raises(ValueError, match="axis_origin_corner"):
        GameParams.from_config(game_config)


def test_start_positions_must_be_on_the_board(game_config: dict) -> None:
    game_config["board_and_agents"]["thief_start"] = [7, 0]
    with pytest.raises(ValueError, match="thief_start"):
        GameParams.from_config(game_config)


def test_start_positions_must_differ(game_config: dict) -> None:
    game_config["board_and_agents"]["thief_start"] = [0, 0]
    with pytest.raises(ValueError, match="distinct"):
        GameParams.from_config(game_config)


def test_last_index_accounts_for_axis_start(game_config: dict) -> None:
    game_config["board_and_agents"].update(axis_start_index=1, thief_start=[4, 4], cop_start=[1, 1])
    assert GameParams.from_config(game_config).last_index == 7


def test_params_are_immutable(params: GameParams) -> None:
    with pytest.raises(AttributeError):
        params.grid_size = 9  # type: ignore[misc]
