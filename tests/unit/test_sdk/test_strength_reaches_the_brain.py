"""`match_day.py warmup` wrote a key the brain never read (T-2538).

`strength.level` lives in its own `[strength]` config section; `_tuning` only
ever read `[strategy.<side>]`. So `ThiefBrain.strength` kept its dataclass
default of `"full"` whatever the config said, and **every sandbagged warm-up
this project has played was played at full strength** — including the ones whose
whole purpose was to avoid showing our real policy to a team we would meet again.

Seventh finished-but-unwired component here, and the one with the worst shape:
the guard that refuses a *counted* match at less than full strength worked
perfectly, so the safe direction was enforced while the protective direction did
nothing, and the operator saw `level = "sandbagged"` written to disk each time.

Noticed by Naji from the *moves* — "they move in the exact same way" — which is
the only place it was visible.
"""

from najamjad_agent.constants import Role
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.movement import legal_moves
from najamjad_agent.domain.params import GameParams
from najamjad_agent.sdk.match_setup import brain_factory
from najamjad_agent.shared.strength import plays_full_strength
from najamjad_agent.strategy.thief_brain import ThiefBrain

PARAMS = GameParams.from_config({
    "board_and_agents": {"grid_size": 7, "cop_start": [0, 0], "thief_start": [3, 3]},
    "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                              "max_moves": 35, "survival_threshold": 35},
})


class _Manager:
    """Only what `brain_factory` reads, so the shipped config cannot mask a bug."""

    def __init__(self, level: str) -> None:
        self._values = {"strength.level": level}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _State:
    def __init__(self, board): self.board = board


class _Facts:
    def __init__(self, **kw): self.__dict__.update(kw)


def _brain(level: str):
    board = Board(PARAMS)
    return brain_factory(_Manager(level))(Role.THIEF, _State(board))


def test_a_sandbagged_config_produces_a_sandbagged_brain() -> None:
    """The defect, stated at the seam where it happened."""
    assert _brain("sandbagged").strength == "sandbagged"


def test_full_is_still_full() -> None:
    """The fix must not silently weaken a counted match — the costly direction."""
    brain = _brain("full")

    assert brain.strength == "full"
    assert plays_full_strength(brain.strength)


def test_an_absent_setting_means_full() -> None:
    """No `[strength]` section is a normal config, not a reason to play weak."""
    assert _brain_default().strength == "full"


def _brain_default():
    board = Board(PARAMS)
    return brain_factory(_Manager(None) if False else _Empty())(Role.THIEF, _State(board))


class _Empty:
    def get(self, key: str, default=None):
        return default


def test_the_two_levels_actually_choose_different_moves() -> None:
    """The observation that found it: they moved identically.

    Asserted where the difference is *supposed* to live — a sharp belief, which
    is the only case `plays_full_strength` gates. A test on a flat belief would
    pass in both worlds, since neither policy can localise a cop it cannot see.
    """
    board = Board(PARAMS)
    belief = dict.fromkeys(board.cells(), 0.0)
    belief[(2, 3)] = 1.0

    differences = 0
    for position in ((4, 4), (1, 1), (5, 2), (6, 6), (0, 3)):
        facts = _Facts(legal=legal_moves(board, position), belief=belief,
                       own_position=position, step=5, sub_game=1,
                       own_scent={}, scent={}, barriers_left=0)
        full = ThiefBrain(board_supplier=lambda: board, strength="full").pick_move(facts)
        weak = ThiefBrain(board_supplier=lambda: board, strength="sandbagged").pick_move(facts)
        differences += full != weak

    assert differences >= 3, "sandbagged still plays the full-strength line"


def test_the_levels_differ_even_when_the_opponent_emits_no_scent() -> None:
    """The case the first fix missed, and the one that actually occurs.

    Gating on `cop = located if full else None` only skipped the safety
    invariant. Against a peer emitting no scent the belief is flat, `_cop_cell`
    returns None regardless, and both levels fell through to the identical blind
    move — so a warm-up against exactly the opponents we most wanted to hide
    from was played at full strength, indistinguishably. uoh-ay26 sent zero
    scent cells across 135 sealed records; this is their regime, not a corner.
    """
    board = Board(PARAMS)
    flat = dict.fromkeys([cell for cell in board.cells() if board.is_open(cell)], 1 / 49)

    differences = 0
    for position in ((4, 4), (1, 1), (5, 2), (6, 6), (0, 3)):
        facts = _Facts(legal=legal_moves(board, position), belief=flat,
                       own_position=position, step=5, sub_game=1,
                       own_scent={}, scent={}, barriers_left=0)
        full = ThiefBrain(board_supplier=lambda: board, strength="full").pick_move(facts)
        weak = ThiefBrain(board_supplier=lambda: board, strength="sandbagged").pick_move(facts)
        differences += full != weak

    assert differences >= 3, "flat belief still collapses both levels onto one policy"
