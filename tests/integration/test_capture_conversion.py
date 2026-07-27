"""Converting a capture against an opponent who does not concede enclosure.

Our cop's measured 100 % capture rate came almost entirely from **barrier
captures** — walling the thief in — and a barrier capture only ends a game if
the thief concedes it. Ours does. The course reference's does not, and most of
the class is built on it: a full six-game rehearsal ended 45-45 with *not one*
of the twelve cop-halves producing a capture.

Three things had to change, and the last two are protocol rather than strategy:

1. A **capture step outranks a barrier** — placing one costs us the move, so
   walling while stood next to the thief trades a capture for a wall.
2. The answer to a capture claim may arrive **at the step it answers**; the
   reference sends its concession as a final message without advancing its
   counter, and our monotonic guard rejected the one message we were waiting for.
3. That answer is a **reply, not a new turn**. Recording its commit as a fresh
   one reads as a peer overwriting history, and we filed `tamper_forfeit`
   against an opponent who had just conceded honestly.

After all three: 90-30, six wins from six, both sides agreeing on every game.
"""

import pytest

from najamjad_agent.constants import Move, Role
from najamjad_agent.domain.turn_ingress import absorb_turn
from najamjad_agent.net.inbox import Inboxes
from najamjad_agent.strategy.cop_brain import CopBrain
from tests.fakes.orchestration import build_state


class Facts:
    """The fields a cop brain reads off a turn."""

    def __init__(self, board, position, belief, barriers_left=14):
        from najamjad_agent.domain.movement import legal_moves

        self.board = board
        self.own_position = position
        self.belief = belief
        self.legal = legal_moves(board, position)
        self.barriers_left = barriers_left
        self.role = "police"


def turn(step: int, **extra) -> dict:
    """A minimally valid opponent turn."""
    return {"step": step, "sender": "them", "hint": "x", "smell_grid": {},
            "commit": f"{step:064d}", **extra}


# ------------------------------------------------------------------- strategy


def test_a_capture_step_outranks_placing_a_barrier():
    """Placing one costs us the move; the orchestrator does one or the other."""
    state = build_state(Role.COP, position=(0, 0))
    brain = CopBrain()
    facts = Facts(state.board, (0, 0), {(0, 1): 0.9})

    assert brain.pick_barrier(facts) is None, "a wall is not worth a capture"
    assert brain.pick_move(facts) is Move.EAST, "step onto the believed cell"


def test_a_faint_belief_does_not_trigger_a_speculative_claim():
    """A wrong claim discloses our cell — the price that stops us claiming
    every turn."""
    state = build_state(Role.COP, position=(0, 0))
    brain = CopBrain()
    facts = Facts(state.board, (0, 0), {(0, 1): 0.02, (6, 6): 0.5})

    assert brain.capture_step_available(facts) is False


def test_the_claim_threshold_is_far_below_the_barrier_threshold():
    """Opposite risk profiles: a barrier is permanent and blocks us too, a step
    is reversible."""
    brain = CopBrain()

    assert brain.claim_threshold < brain.barrier_threshold


def test_barriers_are_still_placed_when_no_capture_is_in_reach():
    """The enclosure game still wins against opponents who concede it."""
    state = build_state(Role.COP, position=(0, 0))
    brain = CopBrain()
    facts = Facts(state.board, (0, 0), {(5, 5): 0.95})

    assert brain.capture_step_available(facts) is False
    assert brain.pick_move(facts) is not Move.STAY, "close the distance instead"


# ------------------------------------------------------------------- protocol


def test_a_claim_answer_may_arrive_at_the_step_it_answers():
    """The reference concedes with a final message at the current step.

    Rejecting it as a replay stalls the game at the exact moment we captured —
    which is what it did, three times in a six-game series.
    """
    inboxes = Inboxes()
    for step in (1, 2, 3):
        assert inboxes.accept("turn", turn(step)).errors == []

    answer = inboxes.accept("turn", turn(3, claim_response={"claim": [1, 1], "caught": True}))

    assert answer.errors == [], "the answer we are waiting for must get through"


def test_an_ordinary_replay_is_still_refused():
    """Allowing answers through must not reopen the guard generally."""
    inboxes = Inboxes()
    for step in (1, 2, 3):
        inboxes.accept("turn", turn(step))

    replayed = inboxes.accept("turn", turn(3))

    assert replayed.errors and "stale or replayed" in replayed.errors[0]


def test_a_concession_is_absorbed_as_a_reply_not_a_duplicate_commit():
    """We branded an honest opponent a forger for conceding.

    Their concession carries the same step, so recording its commit as a fresh
    one raises `ProtocolOrderError` — which we reported as `tamper_forfeit`
    against a game they had scored as our capture. Contradictory reports void
    the game for both (rules 33-35).
    """
    state = build_state(Role.COP, position=(0, 0))
    events: list[tuple] = []
    record = lambda name, **fields: events.append((name, fields))  # noqa: E731

    assert absorb_turn(state, turn(4), record) is None
    problem = absorb_turn(
        state, turn(4, claim_response={"claim": [0, 0], "caught": True}), record
    )

    assert problem is None, f"an honest concession was rejected: {problem}"
    assert any(name == "peer.answered_claim" for name, _ in events)


def test_a_genuine_duplicate_commit_is_still_a_protocol_error():
    """Without a claim answer attached, a re-committed step is what it was."""
    state = build_state(Role.COP, position=(0, 0))
    record = lambda _name, **_fields: None  # noqa: E731

    assert absorb_turn(state, turn(4), record) is None
    problem = absorb_turn(state, turn(4), record)

    assert problem and "protocol error" in problem


@pytest.mark.parametrize("caught", [True, False])
def test_both_answers_are_absorbed_without_complaint(caught: bool):
    """An honest 'no' is as much an answer as an honest 'yes'."""
    state = build_state(Role.COP, position=(0, 0))
    record = lambda _name, **_fields: None  # noqa: E731
    absorb_turn(state, turn(2), record)

    problem = absorb_turn(
        state, turn(2, claim_response={"claim": [0, 0], "caught": caught}), record
    )

    assert problem is None
