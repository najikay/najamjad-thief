"""The step guard, and the one exemption that used to be a hole.

The exemption is real and had to exist: the reference concedes a capture with a
final message *at the step it answers*, without advancing its counter, and a
strict monotonic guard rejected the one message we were waiting for — stalling
the game at the exact moment we had won it.

The way it was written, though, any message carrying a `claim_response` skipped
the sequence check completely: any step number, any number of times. The comment
defending it argued that "an answer is idempotent and the game ends on the first
one", which is true of an answer to a claim we actually made and *not* true of a
field the sender chooses to set. Our endpoint is public (rule 10).
"""

import pytest

from najamjad_agent.net.turn_sequence import TurnSequence


@pytest.fixture()
def sequence() -> TurnSequence:
    return TurnSequence()


def _play(sequence: TurnSequence, steps: range) -> None:
    for step in steps:
        assert sequence.check(step, is_answer=False) is None


def test_a_concession_at_the_step_it_answers_is_admitted(sequence: TurnSequence) -> None:
    """The behaviour the exemption exists for, and it must survive the fix."""
    _play(sequence, range(1, 8))

    assert sequence.check(7, is_answer=True) is None


def test_answers_ride_on_ordinary_turns_many_in_a_row(sequence: TurnSequence) -> None:
    """The regression that a ±1 window caused, pinned with real data.

    The reference attaches `capture_claim` to *every* police move, so the thief
    answers on ordinary move-carrying turns, consecutively. These are the exact
    steps our own archived `events.jsonl` recorded `peer.answered_claim` on in
    one mini-game. Under the ±1 window, 10 of 35 turns were refused — each one a
    dropped turn, a timed-out poll, and the peer's watchdog scoring it against
    us.
    """
    _play(sequence, range(1, 11))

    for step in (11, 12, 13, 14, 15):
        assert sequence.check(step, is_answer=True) is None, f"refused an honest turn at {step}"
    for step in (21, 22, 23, 24, 25, 26, 27):
        _play(sequence, range(sequence.last_step + 1, step))
        assert sequence.check(step, is_answer=True) is None


def test_an_answer_ahead_of_us_advances_the_counter(sequence: TurnSequence) -> None:
    """Because it *is* a turn. Not advancing is what made the window refuse.

    An answer-bearing turn that never moved the mark left every later step
    looking further and further out of range.
    """
    _play(sequence, range(1, 8))

    assert sequence.check(8, is_answer=True) is None
    assert sequence.last_step == 8


def test_a_replayed_step_cannot_be_revived_by_calling_it_an_answer(
    sequence: TurnSequence,
) -> None:
    """The hole: one key used to skip the sequence guard entirely."""
    _play(sequence, range(1, 8))

    refusal = sequence.check(2, is_answer=True)

    assert refusal is not None
    assert "stale or replayed" in refusal


def test_a_stale_step_cannot_be_revived_by_calling_it_an_answer(
    sequence: TurnSequence,
) -> None:
    """Replaying step 2 mid-game was a one-key bypass of the whole guard."""
    _play(sequence, range(1, 8))

    assert sequence.check(2, is_answer=False) is not None, "the ordinary guard still holds"
    assert sequence.check(2, is_answer=True) is not None, "and the exemption must not lift it"


def test_the_same_answer_cannot_be_taken_twice(sequence: TurnSequence) -> None:
    """Once per step. Unlimited repeats is what made this a flood, not a race."""
    _play(sequence, range(1, 8))

    assert sequence.check(7, is_answer=True) is None
    repeat = sequence.check(7, is_answer=True)

    assert repeat is not None
    assert "already accepted" in repeat


def test_a_new_mini_game_may_answer_the_same_step_number(sequence: TurnSequence) -> None:
    """Six mini-games all number their steps from 1.

    Without clearing, game 2's honest concession at step 7 would be refused as
    a duplicate of game 1's — the same class of bug as the step guard that
    never reset between games and meant we could not play more than one
    mini-game against anyone.
    """
    _play(sequence, range(1, 8))
    assert sequence.check(7, is_answer=True) is None

    sequence.begin_sub_game(held_opening=False)
    _play(sequence, range(1, 8))

    assert sequence.check(7, is_answer=True) is None


def test_draining_forgets_the_answers_too(sequence: TurnSequence) -> None:
    """`drain` is the harder reset; leaving answers behind would half-reset it."""
    _play(sequence, range(1, 8))
    assert sequence.check(7, is_answer=True) is None

    sequence.drain()
    _play(sequence, range(1, 8))

    assert sequence.check(7, is_answer=True) is None


def test_the_opening_turn_of_the_next_game_is_still_admitted(
    sequence: TurnSequence,
) -> None:
    """The pre-existing exception, unchanged: step 1 after a finished game.

    Guarded here because the split moved this logic, and a refactor that
    quietly dropped it would cost the whole series rather than one message.
    """
    _play(sequence, range(1, 12))

    assert sequence.check(1, is_answer=False) is None
    assert sequence.last_step == 1


def test_a_replayed_first_turn_is_still_refused(sequence: TurnSequence) -> None:
    """"Step 1 always resets" would have admitted this; `> FIRST_STEP` does not."""
    assert sequence.check(1, is_answer=False) is None

    assert sequence.check(1, is_answer=False) is not None
