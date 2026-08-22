"""The factory ships one brain set, and no dial can swap it (2026-08-22).

This file used to pin the opposite end of a dead rope: that `strength.level`
reached `ThiefBrain.strength` (T-2538 — for weeks it never did, and every
"sandbagged" warm-up played at full strength while the operator watched the
level being written to disk). The levels are collapsed now and the probe
machinery that keyed off them is retired, so what deserves pinning is the
new invariant: **the brains that play a friendly are byte-for-byte the
brains that play the counted series**, chosen by `strategy.cop_class` /
`strategy.thief_class` and by nothing else — no strength wiring, no
preference file, nothing a stale workspace can swap in on match day.
"""

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.params import GameParams
from najamjad_agent.sdk.match_setup import brain_factory
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.thief_brain import ThiefBrain

PARAMS = GameParams.from_config({
    "board_and_agents": {"grid_size": 7, "cop_start": [0, 0], "thief_start": [3, 3]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                              "max_moves": 35, "survival_threshold": 35},
})


class _Manager:
    def __init__(self, values: dict | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _State:
    def __init__(self, board):
        self.board = board
        self.sub_game = 1


def _built(role: Role, values: dict | None = None):
    return brain_factory(_Manager(values))(role, _State(Board(PARAMS)))


def test_the_shipped_brains_carry_no_strength_dial() -> None:
    """The dial is gone, not defaulted — a field nobody reads is the unwired
    shape this project keeps finding, so its absence is the assertion."""
    assert not hasattr(_built(Role.THIEF), "strength")
    assert not hasattr(_built(Role.COP), "strength")


def test_a_stale_strength_setting_changes_nothing_about_the_brain() -> None:
    """A config still carrying `strength.level` builds the same agent."""
    plain = _built(Role.THIEF)
    stale = _built(Role.THIEF, {"strength.level": "sandbagged"})

    assert type(stale) is type(plain) is ThiefBrain


def test_the_configured_cop_class_is_what_every_window_gets() -> None:
    """The seal that carries the deterministic win cannot be swapped out."""
    cop = _built(Role.COP, {"strategy.cop_class": "najamjad_agent.strategy.seal_cop:SealCop"})

    assert type(cop) is SealCop
