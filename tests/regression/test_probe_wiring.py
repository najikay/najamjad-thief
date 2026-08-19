"""Every window the probe can select must build and move, through the real wiring.

`test_probe_selection` proves the choosing is sound in isolation. This proves the
composition root can actually instantiate what it chose and get a legal move out
of it, using this repository's own configuration — and between them they close the
gap where this project's recurring defect lives: a component complete, tested, and
never successfully called at the production edge.

A brain that fails to construct fails at the first turn of a mini-game, and rule
35 scores that as not having played. So this walks all six windows in both modes,
and every saved pick the counted path can load.

`cwd` is moved to a tmp directory because that is where `probe.load_choice` looks;
absolute paths are captured first, so the config still resolves.
"""

import json
from pathlib import Path

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.domain.params import GameParams
from najamjad_agent.sdk.match_setup import brain_factory
from najamjad_agent.sdk.probe import save_choice
from najamjad_agent.sdk.state_setup import build_state
from najamjad_agent.shared.config import ConfigManager
from najamjad_agent.strategy.variants import COPS, THIEVES

REPO = Path(__file__).resolve().parents[2]
ROLE_DIR = REPO / ("config/police" if (REPO / "config/police").is_dir() else "config/thief")
PARAMS = GameParams.from_config(json.loads((REPO / "config/game.json").read_text(encoding="utf-8")))


def facts_for(state):
    """The turn facts a brain reads, in the shape the orchestrator supplies."""

    class Facts:
        board = state.board
        belief = state.belief.as_dict()
        own_position = state.own_position
        legal = tuple(legal_moves(state.board, state.own_position))
        barriers_left = state.barriers_left
        step = state.step

    return Facts()


@pytest.fixture
def manager():
    return ConfigManager.load(ROLE_DIR)


@pytest.mark.parametrize("level", ["sandbagged", "full"])
def test_every_window_builds_and_returns_a_legal_move(manager, level, tmp_path, monkeypatch) -> None:
    """Six windows, both roles, both modes — construct, move, and offer a wall."""
    monkeypatch.chdir(tmp_path)
    manager.overlay({"strength": {"level": level}})
    build = brain_factory(manager)

    for window in (1, 2, 3, 4, 5, 6):
        for role in (Role.COP, Role.THIEF):
            state = build_state(PARAMS, role, window)
            brain = build(role, state)
            move = brain.pick_move(facts_for(state))
            assert isinstance(move, Move), f"{role} window {window} returned {move!r}"
            if role is Role.COP:
                cell = brain.pick_barrier(facts_for(state))
                assert cell is None or PARAMS.contains(cell)


def test_every_saved_pick_builds_at_full_strength(manager, tmp_path, monkeypatch) -> None:
    """The counted path: whatever the probe chose has to instantiate for real."""
    monkeypatch.chdir(tmp_path)
    manager.overlay({"strength": {"level": "full"}, "network": {"opponent_group_id": "them"}})

    for cop in COPS:
        for thief in THIEVES:
            save_choice(tmp_path, "them", {"cop": cop.name, "thief": thief.name})
            build = brain_factory(manager)
            for role, window in ((Role.COP, 2), (Role.THIEF, 1)):
                state = build_state(PARAMS, role, window)
                brain = build(role, state)
                assert isinstance(brain.pick_move(facts_for(state)), Move), (
                    f"{cop.name}/{thief.name} failed to move as {role}")
