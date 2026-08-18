"""The cop is judged on board SHAPE, not on captures (T-2721).

Every capture-based bench was green on 2026-08-18 while the second seal had
stopped happening entirely — Naji saw it on the dashboard, no test did. The
reason is structural: against the opponents these suites use, the cop captures
before the seal ever has to work, so the seal is never exercised and its absence
is invisible. A cop that has forgotten how to wall still passes them all.

So this file asserts the room shrinks. `smallest_room` is the smallest region
the thief was ever confined to, and the exact win table is the yardstick:
fifteen cells fall, sixteen hold.

The greedy evader is the case that matters and it is currently a KNOWN FAILURE,
recorded rather than hidden: nine barriers spent and a 19-cell room, so the
walls bought nothing. It is pinned at the measured value so an improvement is
visible and a regression is caught; when the seal is fixed this bound tightens.
"""

import json
import random

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.belief import BeliefGrid
from najamjad_agent.domain.board import Board
from najamjad_agent.domain.game_state import GameState
from najamjad_agent.domain.ledger import CommitLedger
from najamjad_agent.domain.movement import apply_move, legal_moves, place_barrier
from najamjad_agent.domain.params import GameParams
from najamjad_agent.domain.scent import ScentField
from najamjad_agent.domain.turn_ingress import absorb_turn, decay_after_full_turn
from najamjad_agent.strategy.seal_cop import SealCop
from najamjad_agent.strategy.territory import component
from tests.regression.cop_duel import Facts, _their_frame

"""Does the cop actually SEAL? Measures board shape, not captures."""


with open("config/game.json") as _handle:
    params = GameParams.from_config(json.load(_handle))


class Runner:
    """Greedy evader: maximises distance from the cop. Weak on purpose."""
    def pick_move(self, facts):
        best, far = Move.STAY, -1
        for m in facts.legal:
            dr, dc = facts.board.delta_for(m)
            land = (facts.own_position[0] + dr, facts.own_position[1] + dc)
            d = Board.manhattan(land, facts.cop_position)
            if d > far:
                best, far = m, d
        return best


class Corner:
    """Sits in a corner — what anrbj666's thief effectively did."""
    def pick_move(self, facts):
        here = facts.own_position
        for want in (Move.NORTH, Move.WEST):
            if want in facts.legal:
                dr, dc = facts.board.delta_for(want)
                if (here[0] + dr, here[1] + dc) != facts.cop_position:
                    return want
        return Move.STAY


class Wanderer:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)

    def pick_move(self, facts): return self.r.choice(list(facts.legal))


def play(thief_brain, label):
    board = Board(params)
    st = GameState(board=board, role=Role.COP, sub_game=1, own_position=params.cop_start,
                   belief=BeliefGrid(board, start=params.thief_start),
                   own_scent=ScentField(board_size=board.size),
                   opponent_scent=ScentField(board_size=board.size), ledger=CommitLedger(sub_game=1))
    cop, thief, walls = params.cop_start, tuple(params.thief_start), []
    brain = SealCop()
    smallest, captured, at = 49, False, None
    for step in range(1, 36):
        ft = Facts(st, {}, 0)
        ft.own_position, ft.cop_position = thief, cop
        ft.legal = legal_moves(st.board, thief)
        ft.board = st.board
        mv = thief_brain.pick_move(ft)
        if mv in ft.legal:
            dr, dc = st.board.delta_for(mv)
            land = (thief[0] + dr, thief[1] + dc)
            if st.board.is_open(land):
                thief = land
        st.step = step
        absorb_turn(st, {"step": step, "sender": "thief", "commit": f"{step:064x}",
                         "smell_grid": _their_frame(thief, params)}, lambda n, **f: None)
        decay_after_full_turn(st)
        if cop == thief:
            captured, at = True, step
            break
        f = Facts(st, st.belief.as_dict(), params.max_barriers - len(walls))
        f.own_position = cop
        f.legal = legal_moves(st.board, cop)
        wall = brain.pick_barrier(f) if len(walls) < params.max_barriers else None
        if wall is not None:
            st.board = place_barrier(st.board, Role.COP, cop, wall).board
            walls.append(wall)
        else:
            m = brain.pick_move(f)
            if m not in f.legal:
                m = Move.STAY if Move.STAY in f.legal else f.legal[0]
            cop = apply_move(st.board, cop, m)
            if cop == thief:
                captured, at = True, step
                break
        smallest = min(smallest, len(component(st.board, thief)))
    verdict = "WON" if captured else ("sealed" if smallest <= 15 else "NO SEAL")
    print(f"  {label:<22} walls={len(walls):>2}  smallest_room={smallest:>2}  "
          f"{'captured@'+str(at) if captured else 'survived':<13} {verdict}")
    return smallest, len(walls), captured




WINNABLE = 15


def test_the_seal_is_not_silently_gone() -> None:
    """At least one grade of opponent must still see barriers placed."""
    walls = [play(Runner(), "greedy evader")[1], play(Wanderer(1), "wanderer")[1]]

    assert max(walls) > 0, "the cop placed no barriers at all — the seal is gone"


def test_the_greedy_evader_is_still_the_known_failure() -> None:
    """Pinned at what we measure today, so progress and regress both show.

    Seven barriers spent and the room never below 42 — against a thief that
    simply runs, the column cut never completes, so the row cut never happens
    and the walls buy nothing. This is the open defect.

    It is pinned as *two* separate facts on purpose. `walls >= 5` catches the
    seal being switched off, which is how a guard added on 2026-08-18 went
    unnoticed by every capture bench while the cop placed a single wall and
    wandered. `smallest <= 45` catches the room never shrinking at all. Tighten
    the second to `<= WINNABLE` when the approach is fixed; do not loosen either
    to make a change pass.
    """
    smallest, walls, captured = play(Runner(), "greedy evader")

    assert not captured, "the evader is now caught — tighten this test"
    assert walls >= 5, f"only {walls} barriers spent — the cop stopped sealing"
    assert smallest <= 45, f"room never shrank below {smallest} — the column cut is broken"


def test_a_wandering_thief_is_still_converted() -> None:
    """The seal must not cost us the captures we already had."""
    assert any(play(Wanderer(seed), "w")[2] for seed in (1, 2, 3))
