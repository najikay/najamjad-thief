"""Deciding whether an inbound turn belongs in this game, at this step.

Split from `Inboxes` at the file budget, and it stands on its own: this is the
only thing in the project that answers "have we seen this step before", and
that answer has cost us games in both directions — once by rejecting a turn the
opponent legitimately sent, once by admitting anything that merely claimed to
be an answer.
"""

from __future__ import annotations

import secrets
import threading

from .delivery import decide
from .sub_game_boundary import FIRST_STEP


class TurnSequence:
    """The monotonic step guard, plus the one exemption it has to make."""

    def __init__(self) -> None:
        """Start before any mini-game: nothing accepted, nothing answered."""
        self._last_step = -1
        #: Every step already applied, keyed by the commit that sealed it. The
        #: kit's §7.1 contract dedupes on the commit, because it is the only
        #: field that separates a redelivery (absorb) from an equivocation
        #: (evidence). A step-only guard calls both "stale" and refuses both,
        #: which is the failure the contract exists to forbid.
        self._played: dict[int, str] = {}
        #: Steps whose capture-claim answer we have already taken. An answer is
        #: exempt from the monotonic guard, so without this the exemption is a
        #: standing invitation to replay.
        self._answered: set[int] = set()
        self._lock = threading.Lock()

    @property
    def last_step(self) -> int:
        """The highest step accepted so far."""
        return self._last_step

    def check(self, step: int, is_answer: bool, commit: str = "") -> str | None:
        """A refusal reason, or None when the message may proceed.

        `commit` is optional so older call sites keep working; without one the
        delivery contract cannot be applied and the monotonic guard decides
        alone, exactly as it did before.
        """
        return self._check_answer(step) if is_answer else self._check_turn(step, commit)

    def verdict(self, step: int, commit: str) -> str:
        """The §7.1 decision for an arriving turn, without changing any state.

        Separate from `check` because two of the six decisions are not refusals
        and not acceptances either: an `absorb` must leave the sender believing
        it was delivered while adding nothing to the queue, and an
        `equivocation` is evidence rather than a routine rejection.
        """
        with self._lock:
            return decide(dict(self._played), self._last_step + 1, step, commit)

    def _check_turn(self, step: int, commit: str = "") -> str | None:
        """Reject replayed or stale turns before they reach the game state.

        Step 1 is the exception, and it has to be: every mini-game restarts
        numbering at 1, so after a game ending at step 11 the next game's
        opening turn is a legitimate step 1 that this guard would otherwise
        read as a replay.

        The transport also clears the mark between mini-games, but that alone
        is a race — the peer who finishes first sends its next game's opening
        turn before the slower peer has reset, and the turn is dropped by a
        guard that is merely a moment out of date. Whoever wins that race
        should not decide whether the series continues.

        Nothing on the wire distinguishes the two cases: the reference's
        `TurnMessage` has no sub-game field, and it builds messages with
        `cls(**data)`, so adding one would make every turn we send raise a
        `TypeError` in their process. Step 1 is the only signal available, and
        treating it as "a new mini-game started" costs only the ability to
        detect a replayed *first* turn — whose payload is sealed and whose
        duplicate the game's own state machine refuses anyway.
        """
        with self._lock:
            if (commit and step in self._played
                    and secrets.compare_digest(self._played[step], commit)):
                # A redelivery of a step we applied. Not stale, not an error:
                # the network doing exactly what at-least-once means.
                return None
            if step == FIRST_STEP and self._last_step > FIRST_STEP:
                # A game that has already run past its opening turn cannot
                # receive another one; this is the next mini-game beginning.
                # Requiring `> FIRST_STEP` keeps a replayed *first* turn
                # rejected, which a bare "step 1 always resets" would not.
                self._last_step = step
                return None
            if step <= self._last_step:
                if commit and step in self._played:
                    return (f"step {step} was already sealed as "
                            f"{self._played[step][:16]} and arrived again as "
                            f"{commit[:16]} — equivocation, not a redelivery")
                return f"step {step} is stale or replayed (last accepted was {self._last_step})"
            self._last_step = step
            if commit:
                self._played[step] = commit
        return None

    def _check_answer(self, step: int) -> str | None:
        """Admit a capture-claim answer, without exempting it from the sequence.

        The exemption exists because the reference concedes a capture with a
        final message **at the step it answers**, without advancing its counter,
        and a strict monotonic guard rejected the one message we were waiting
        for — stalling the game at the exact moment we had won it.

        It used to be unconditional: any message carrying `claim_response`
        skipped the sequence check completely, at any step, any number of times.
        Our endpoint is public (rule 10), so that was a one-key bypass of the
        whole guard.

        **The first narrowing was wrong in the other direction.** It admitted
        only `last_step ± 1` and never advanced `last_step`, on the assumption
        that an answer is always a final concession. It is not: the reference
        attaches `capture_claim` to *every* police move, so the thief answers on
        ordinary, move-carrying turns, many of them consecutively. Replaying our
        own archived matches through that version refused 10 of 35 turns in one
        mini-game and 14 of 35 in another — each refusal a dropped turn, a
        timed-out poll, and the peer's watchdog scoring it against us. It
        reintroduced the very stall it inherited.

        So the rule is now the ordinary one plus a *single* exception: an answer
        arriving at the step we last accepted is taken once. Anything ahead of
        that is a normal turn and advances the counter like any other; anything
        behind it is stale and refused, which is what closes the bypass.
        """
        with self._lock:
            if step == self._last_step:
                if step in self._answered:
                    return f"claim answer for step {step} was already accepted"
                self._answered.add(step)
                return None
        # Not the same-step concession, so it is an ordinary turn that happens
        # to carry an answer. Outside the lock: `_check_turn` takes it too.
        return self._check_turn(step)

    def begin_sub_game(self, held_opening: bool) -> None:
        """Reset for the next mini-game, keeping an opening turn already in hand."""
        with self._lock:
            self._last_step = FIRST_STEP if held_opening else -1
            self._played.clear()
            # Each mini-game restarts numbering, so last game's answers must not
            # make this game's legitimate ones look like duplicates.
            self._answered.clear()

    def drain(self) -> None:
        """Forget everything: the between-games reset."""
        with self._lock:
            self._last_step = -1
            self._played.clear()
            self._answered.clear()
