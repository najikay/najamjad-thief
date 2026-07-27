"""Config-named components (T-2227).

The documented promise in `docs/EXTENDING.md` is that a brain can be replaced
without editing the agent. These tests hold that promise to the example the
document actually prints, so the two cannot drift apart.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.sdk.match_setup import brain_factory
from najamjad_agent.sdk.plugins import PluginError, load_plugin, resolve
from najamjad_agent.strategy.cop_brain import CopBrain
from najamjad_agent.strategy.thief_brain import ThiefBrain
from tests.fakes.orchestration import build_state


class FakeManager:
    """Just the `get` the factory uses."""

    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_a_dotted_path_resolves_to_the_object():
    assert load_plugin("najamjad_agent.constants:Move") is Move


def test_a_path_without_a_colon_is_refused_rather_than_guessed():
    """`a.b.C` could mean a module or an attribute; guessing turns a typo into
    a silently different object."""
    with pytest.raises(PluginError, match="must be 'module.path:Attribute'"):
        load_plugin("najamjad_agent.constants.Move")


def test_an_unimportable_module_names_itself_in_the_error():
    with pytest.raises(PluginError, match="no_such_module"):
        load_plugin("no_such_module:Thing")


def test_a_missing_attribute_names_itself_in_the_error():
    with pytest.raises(PluginError, match="NoSuchBrain"):
        load_plugin("najamjad_agent.constants:NoSuchBrain")


def test_nothing_configured_means_the_shipped_default():
    assert resolve(None, CopBrain) is CopBrain
    assert resolve("", CopBrain) is CopBrain


def test_the_shipped_brains_are_used_when_no_plugin_is_named():
    build = brain_factory(FakeManager())
    state = build_state(Role.COP)

    assert isinstance(build(Role.COP, state), CopBrain)
    assert isinstance(build(Role.THIEF, state), ThiefBrain)


def test_the_documented_example_plugin_loads_from_config_and_plays():
    """The DoD of T-2227: the plugin in `docs/EXTENDING.md` loads via config.

    It is also asked for a move, because a plugin that imports and then fails on
    contact would satisfy a weaker test while being useless.
    """
    build = brain_factory(FakeManager(**{"strategy.thief_brain": "plugins.wall_hugger:WallHugger"}))
    state = build_state(Role.THIEF)
    brain = build(Role.THIEF, state)

    assert type(brain).__name__ == "WallHugger"
    move = brain.pick_move(_Facts(state))
    assert isinstance(move, Move)
    assert brain.pick_barrier(_Facts(state)) is None


def test_the_cop_side_is_unaffected_by_a_thief_plugin():
    """One override must not quietly replace both roles."""
    build = brain_factory(FakeManager(**{"strategy.thief_brain": "plugins.wall_hugger:WallHugger"}))

    assert isinstance(build(Role.COP, build_state(Role.COP)), CopBrain)


def test_a_bad_plugin_path_fails_while_wiring_not_mid_match():
    """The Assignment 6 failure mode: a config value naming something that does
    not exist, discovered under time pressure."""
    with pytest.raises(PluginError):
        brain_factory(FakeManager(**{"strategy.cop_brain": "plugins.nope:Missing"}))


class _Facts:
    """The handful of fields a brain reads off a turn."""

    def __init__(self, state):
        from najamjad_agent.domain.movement import legal_moves

        self.board = state.board
        self.own_position = state.own_position
        self.legal = legal_moves(state.board, state.own_position)
        self.belief = {}
