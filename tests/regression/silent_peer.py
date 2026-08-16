"""The belief a silent opponent leaves us, computed by the production code.

`run_duel`'s default hands the thief the cop's exact cell, which is the right
default for asking "is our *policy* wrong". It is the wrong instrument for the
question that actually cost us the series: uoh-sqak send no scent, no hints and
no observations of any kind, so the thief was never told where the cop was and
the perfect-information duel could not see that at all. It reported a healthy
survival for a strategy that was, against them, blind.

So this drives a **real `GameState` through the real `absorb_turn` and
`decay_after_full_turn`** rather than reimplementing the belief update. That is
deliberate and it is the repo's own hard-won rule: five bugs have hidden behind
test doubles kinder than the thing they stood in for. A hand-rolled belief here
would be exactly such a double — it would model the fix working, which is not
evidence that the fix works.

The messages fed in are the ones uoh-sqak actually sent, reduced to what their
agent emits: a commit, a step, a capture claim naming the swept cell, and a
barrier declaration. No `smell_grid`. No `hint`. Nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

from najamjad_agent.constants import Role
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.game_state import GameState
from najamjad_agent.domain.ledger import CommitLedger
from najamjad_agent.domain.params import GameParams, Position
from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.turn_ingress import absorb_turn, decay_after_full_turn


class SilentPeerBelief:
    """Belief built only from declarations a silent peer is still obliged to make.

    Input:  the agreed params, plus the cop's scripted cells and barriers.
    Output: callable as `run_duel`'s `belief_for` hook — `(cop, step, thief)`
            returns the distribution our agent would genuinely hold at that step.
    Setup:  construct once per duel; it carries the belief across steps, because
            a filter that is reset every step is not a filter.
    """

    def __init__(
        self,
        params: GameParams,
        cop_line: Sequence[Position],
        barriers: Sequence[Position] = (),
        emit_scent: bool = False,
    ) -> None:
        """Build the thief-side state a real mini-game would start from."""
        board = Board(params)
        self._state = GameState(
            board=board,
            role=Role.THIEF,
            sub_game=1,
            own_position=params.thief_start,
            belief=BeliefGrid(board),
            own_scent=ScentField(board_size=board.size),
            opponent_scent=ScentField(board_size=board.size),
            ledger=CommitLedger(sub_game=1),
        )
        self._cop_line = tuple(cop_line)
        # Keyed by the step each wall was declared on, so an archived line keeps
        # its real timing — see `run_duel` for what compacting it costs.
        self._barriers = (
            {int(step): tuple(cell) for step, cell in barriers.items()}
            if isinstance(barriers, dict)
            else {step: tuple(cell) for step, cell in enumerate(barriers, start=1)}
        )
        self._emit_scent = emit_scent
        self.events: list[str] = []

    def _message(self, cop: Position, step: int) -> dict[str, object]:
        """One turn as uoh-sqak's agent actually sends it.

        A claim on every step is theirs, not an embellishment: a claim forces a
        cryptographically truthful yes/no, so claiming each swept cell buys a
        free bit per turn. It also, unavoidably, tells us exactly where they are.
        """
        message: dict[str, object] = {
            "step": step,
            "sender": "police",
            "commit": f"{step:064x}",
            "capture_claim": [cop[0], cop[1]],
        }
        wall = self._barriers.get(step)
        if wall is not None:
            message["barrier_placed"] = list(wall)
        if self._emit_scent:
            message["smell_grid"] = {f"{cop[0]},{cop[1]}": 0.9}
        return message

    def __call__(self, cop: Position, step: int, thief: Position) -> dict[Position, float]:
        """Absorb this step's declarations and return the resulting belief."""
        self._state.own_position = thief
        self._state.step = step
        absorb_turn(self._state, self._message(cop, step), self._record)
        decay_after_full_turn(self._state)
        return self._state.belief.as_dict()

    def _record(self, name: str, **_fields: object) -> None:
        """Collect event names so a test can assert the evidence path ran."""
        self.events.append(name)

    @property
    def peak(self) -> Position | None:
        """The cell the belief currently names as the cop's."""
        return self._state.belief.peak()
