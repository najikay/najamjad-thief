"""The pocket is won by locking them in, not only by landing on them.

`_win` scored exactly one terminal state, `cop == thief`, and `_steps` includes
the agent's own cell — so the thief always had STAY available, its option list
was never empty, and `all(...)` was never vacuous. Between them, an immobilised
thief was not a state the solver could represent. It could only ever hunt a
step-on capture, which a dodging thief prevents forever on a grid; `solver.py`
has always said so and is right.

Live cost, ahk-yosi 2026-08-21 g02: the cop built the pocket, reached the cell
its own plan named, placed both remaining barriers from there — and then paced
[1,5]<->[1,6] for five turns and finished on [2,6] at step 34, beside a thief it
had already cornered. Three windows, same ending.

Rule 47 in the words both teams agreed on 2026-08-21: a thief with no legal
*move* is captured; standing still is not an escape. The cop's own body covers
one exit, so at most three barriers finish any pocket — which is the whole
reason the seal is built.
"""

from __future__ import annotations

from najamjad_agent.domain.endgame import forced_capture, winning_action

POCKET = frozenset((r, c) for r in range(3) for c in range(3))


def test_movement_alone_still_wins_nothing() -> None:
    """Unchanged, and the reason barriers exist: no budget, no forced win."""
    assert not forced_capture(POCKET, (1, 1), (0, 0), frozenset(), 0, plies=20)


def test_one_barrier_forces_the_win_in_a_three_by_three() -> None:
    """The deterministic result the seal is built to reach.

    Every one of these read False before immobilisation was a win condition,
    which is why a cop with barriers in hand kept looking for a capture it could
    not force.
    """
    for budget in (1, 2, 3):
        assert forced_capture(POCKET, (1, 1), (0, 0), frozenset(), budget, plies=20)


def test_it_commits_to_the_lock_rather_than_chasing() -> None:
    """And the action it picks is the wall, not a step it cannot cash."""
    action = winning_action(POCKET, (1, 1), (0, 0), frozenset(), 1, plies=20)

    assert action is not None
    assert action[0] == "wall"


def test_a_one_step_capture_still_outranks_the_lock() -> None:
    """Landing on them ends it now; a lock takes turns we might not have."""
    action = winning_action(POCKET, (0, 1), (0, 0), frozenset(), 3, plies=20)

    assert action == ("move", (0, 0))


def test_standing_still_is_not_an_escape_but_is_still_a_choice() -> None:
    """Both halves matter.

    A thief with somewhere to go may still choose to stay, and the cop has to
    beat that too — so staying stays in the option list while any move exists.
    It stops being a rescue only when nothing else is left, which is exactly
    what rule 47 says.
    """
    open_room = frozenset((r, c) for r in range(4) for c in range(4))

    assert not forced_capture(open_room, (3, 3), (0, 0), frozenset(), 0, plies=12)
