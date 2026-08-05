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


def test_an_answer_one_step_either_side_is_admitted(sequence: TurnSequence) -> None:
    """A window, not an equality, and deliberately so.

    Our own counter can move by one between making the claim and their reply
    landing. Insisting on the exact step would resurrect the stall this whole
    exemption was written to cure — trading a replay hole for a lost game.
    """
    _play(sequence, range(1, 8))

    assert sequence.check(6, is_answer=True) is None
    assert sequence.check(8, is_answer=True) is None


def test_an_answer_at_an_arbitrary_step_is_refused(sequence: TurnSequence) -> None:
    """The hole. Any step at all used to be accepted, unconditionally."""
    _play(sequence, range(1, 8))

    refusal = sequence.check(999, is_answer=True)

    assert refusal is not None
    assert "answers no live turn" in refusal


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
