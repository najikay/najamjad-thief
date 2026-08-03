"""Tests for the turn alternation bound.

Extracted from `MatchRunner` and tested directly, because the two things that
can go wrong here — playing the wrong side first, and never stopping — are both
invisible when the loop is only exercised through a full match.
"""

from najamjad_agent.constants import EndReason
from najamjad_agent.domain.turn_loop import run_turn_loop


class Conductor:
    """A conductor that ends the game after a fixed number of acts."""

    def __init__(self, moves_first: bool, ends_after: int | None = None) -> None:
        self.moves_first = moves_first
        self._ends_after = ends_after
        self.acts: list[str] = []

    def _act(self, name: str) -> EndReason | None:
        self.acts.append(name)
        if self._ends_after is not None and len(self.acts) >= self._ends_after:
            return EndReason.CAPTURE
        return None

    def take_turn(self) -> EndReason | None:
        return self._act("ours")

    def receive_turn(self) -> EndReason | None:
        return self._act("theirs")


def test_moving_first_means_we_act_first() -> None:
    conductor = Conductor(moves_first=True, ends_after=2)

    assert run_turn_loop(conductor, max_moves=35) is EndReason.CAPTURE
    assert conductor.acts == ["ours", "theirs"]


def test_moving_second_means_they_act_first() -> None:
    conductor = Conductor(moves_first=False, ends_after=2)

    run_turn_loop(conductor, max_moves=35)

    assert conductor.acts == ["theirs", "ours"]


def test_the_first_ending_act_stops_the_loop() -> None:
    """A capture on our move must not be followed by their reply."""
    conductor = Conductor(moves_first=True, ends_after=1)

    assert run_turn_loop(conductor, max_moves=35) is EndReason.CAPTURE
    assert conductor.acts == ["ours"]


def test_a_peer_that_answers_forever_still_runs_out_of_moves() -> None:
    """Survival is decided by the agreed budget, not by the opponent's patience."""
    conductor = Conductor(moves_first=True)

    assert run_turn_loop(conductor, max_moves=35) is None
    assert len(conductor.acts) == 2 * (35 + 1)
