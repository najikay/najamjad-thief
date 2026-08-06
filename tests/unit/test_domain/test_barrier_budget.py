"""Their barriers are declarations, not instructions — and they have a budget.

`movement.place_barrier` refuses *our* placement past `max_barriers`. Nothing
checked theirs, so we banked every wall a peer cared to declare: 48 in one
series against an agreed 14. Rule 47 is what makes that expensive rather than
merely untidy — enough walls seal the thief into a pocket, and immobilisation
scores as a capture.
"""

import pytest

from najamjad_agent.constants import Role
from najamjad_agent.domain.turn_ingress import absorb_turn
from tests.fakes.orchestration import build_state


@pytest.fixture()
def events() -> list[dict]:
    return []


@pytest.fixture()
def state():
    return build_state(Role.THIEF)


def _declare(state, events, cell, step=1):
    absorb_turn(
        state,
        {"step": step, "commit": f"{step:064x}", "barrier_placed": list(cell)},
        lambda name, **fields: events.append({"event": name, **fields}),
    )


def _cells(limit):
    return [(row, col) for row in range(7) for col in range(7)][:limit]


def test_declarations_within_the_budget_are_honoured(state, events) -> None:
    """The ordinary case must keep working; this is not a reason to distrust."""
    for step, cell in enumerate(_cells(5), start=1):
        _declare(state, events, cell, step)

    assert state.board.barrier_count == 5
    assert [e for e in events if e["event"] == "barrier.observed"]


def test_the_agreed_quota_is_the_ceiling(state, events) -> None:
    """14 is what both sides signed. The 15th wall does not go on the board."""
    agreed = state.board.params.max_barriers

    for step, cell in enumerate(_cells(agreed + 10), start=1):
        _declare(state, events, cell, step)

    assert state.board.barrier_count == agreed


def test_going_over_budget_is_recorded_not_silently_dropped(state, events) -> None:
    """Refusing quietly would leave nothing to show in a rules 33-35 dispute."""
    agreed = state.board.params.max_barriers

    for step, cell in enumerate(_cells(agreed + 3), start=1):
        _declare(state, events, cell, step)

    over = [e for e in events if e["event"] == "barrier.over_budget"]
    assert len(over) == 3
    assert over[0]["agreed"] == agreed
    assert over[0]["standing"] == agreed


def test_a_peer_cannot_wall_us_in_past_the_budget(state, events) -> None:
    """The reason this is self-defence rather than bookkeeping.

    Honouring unlimited walls lets a peer seal the thief into a pocket, and
    rule 47 scores immobilisation as a capture — so believing them costs the
    whole mini-game, while disbelieving them costs at worst a disagreement we
    have loudly recorded.
    """
    from najamjad_agent.domain.capture import is_immobilised

    agreed = state.board.params.max_barriers
    # Spend the quota far away, then try to close the four cells around us.
    for step, cell in enumerate(_cells(agreed), start=1):
        _declare(state, events, cell, step)
    here = state.own_position
    for step, cell in enumerate(
        [(here[0] - 1, here[1]), (here[0] + 1, here[1]),
         (here[0], here[1] - 1), (here[0], here[1] + 1)],
        start=agreed + 1,
    ):
        _declare(state, events, cell, step)

    assert not is_immobilised(state.board, here)
