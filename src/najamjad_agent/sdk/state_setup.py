"""Building one mini-game's state from the terms both sides agreed to.

Split out of `match_setup` because it is the only piece of that wiring that
reads the *negotiated* half of the configuration rather than our private half,
and because it is where a signed term quietly failing to arrive would do the
most damage.

That is not hypothetical. Both `ScentField`s here used to be constructed on the
class's own defaults — no decay, no centre intensity, no grid size passed in.
Those defaults happen to equal the values in `config/game.json`, so the omission
was invisible: every match played correctly, and a renegotiated pheromone term
would have been signed, hashed into the handshake fingerprint, echoed back to
the opponent, and then not used by the agent that agreed to it.
"""

from typing import Any

from ..constants import Role
from ..domain.belief import BeliefGrid
from ..domain.board import Board
from ..domain.emission import DEFAULT_GRID_SIZE, EmissionPolicy
from ..domain.fair_play import FairPlayMonitor
from ..domain.game_state import GameState
from ..domain.ledger import CommitLedger
from ..domain.params import GameParams, Position
from ..domain.scent import ScentField
from ..domain.scent_models import ScentModel
from .step_zero_setup import declaration_sealer


def state_factory(manager: Any = None, meter: Any = None, emit: Any = None) -> Any:
    """The mini-game builder, honouring the negotiated and configured terms.

    Mirrors `brain_factory`: configuration is read **once, at wiring time**, so a
    bad `[emission]` mode stops the agent booting rather than surfacing thirty
    steps into a match.

    The step-0 declaration is sealed here rather than in the runner, because
    this is where a mini-game's ledger is born and the only place that already
    holds both the configuration it describes and the ledger it goes into
    (rule 53). It must happen before the first move, and a state handed back
    from here has not played one yet.
    """
    pheromones = dict(manager.get("pheromones", {}) or {}) if manager else {}
    emission = EmissionPolicy.from_config(
        dict(manager.get("emission", {}) or {}) if manager else {},
        grid_size=int(pheromones.get("pheromone_grid_size", DEFAULT_GRID_SIZE)),
    )
    seal_step_zero = declaration_sealer(manager, meter, emit)

    def build(params: GameParams, role: Role, sub_game: int) -> GameState:
        """A fresh mini-game state; nothing may leak between sub-games."""
        state = build_state(params, role, sub_game, emission=emission, pheromones=pheromones)
        seal_step_zero(state, role, sub_game)
        return state

    return build


def build_state(
    params: GameParams,
    role: Role,
    sub_game: int,
    emission: EmissionPolicy | None = None,
    pheromones: dict[str, Any] | None = None,
) -> GameState:
    """A fresh mini-game state; nothing may leak between sub-games.

    `pheromones` carries the *agreed* emission terms. They used to be dropped
    on the floor here — both fields were built on `ScentField`'s own defaults,
    which happen to equal the values in `config/game.json` and so hid the
    omission completely. A renegotiated decay or centre intensity would have
    been signed, locked into the handshake fingerprint, and then not used.
    """
    board = Board(params)
    start = params.cop_start if role is Role.COP else params.thief_start
    terms = dict(pheromones or {})
    scent = lambda: ScentField(  # noqa: E731 - two identical fields, one spec
        board_size=board.size,
        grid_size=int(terms.get("pheromone_grid_size", DEFAULT_GRID_SIZE)),
        decay=float(terms.get("pheromone_decay", 0.10)),
        centre_intensity=float(terms.get("pheromone_center_intensity", 0.9)),
        # **Which physics both peers are running.** `ScentField` defaults to
        # `BOOK`, and nothing here used to override it, so we emitted a radial
        # relative-falloff field while the rest of the league emits the
        # subtractive-Chebyshev one. Nothing crashes: the scent is not part of
        # the commit, so audits still pass — both sides simply infer the wrong
        # position from each other's grid, for the whole series, and each
        # concludes the other is buggy.
        #
        # Verified against the interop kit's CORE `pheromone.json` on
        # 2026-08-05: our `REFERENCE` model reproduces its centre and corner
        # fields exactly, and `BOOK` does not. Configurable because the model is
        # a term both peers must agree on, and a team that has standardised on
        # the book's own variant can still be matched by changing one key.
        model=ScentModel(str(terms.get("pheromone_model", ScentModel.REFERENCE.value))),
    )
    return GameState(
        board=board,
        role=role,
        sub_game=sub_game,
        own_position=start,
        # Seeded with where the opponent actually starts. Both starts are signed
        # terms of `config/game.json`, so this is knowledge the rules give us,
        # not an assumption — and opening uniform instead let a thief walk into
        # a cop standing beside it on turn one.
        belief=BeliefGrid(board, start=opponent_start(params, role)),
        own_scent=scent(),
        opponent_scent=scent(),
        ledger=CommitLedger(sub_game=sub_game),
        emission=emission or EmissionPolicy(),
        # One monitor per mini-game, because the barrier budget and the step
        # numbering both reset with it. Watching the opponent is not optional
        # equipment: commit-reveal proves they did not rewrite what they did,
        # and this is the only thing that asks whether they were allowed to.
        fair_play=FairPlayMonitor(max_barriers=params.max_barriers),
    )


def opponent_start(params: GameParams, role: Role) -> Position:
    """Where the other side begins, from the agreed terms rather than a guess.

    Both starts are fixed in the signed `config/game.json` and byte-identical on
    both sides, so this is information the rules hand us at step 0. Keyed off
    our own role so the two repos cannot disagree about whose cell is whose.
    """
    return params.cop_start if role is Role.THIEF else params.thief_start
