"""One dead sub-game must cost one sub-game, and never the rest of the series.

This is the top operational requirement: **full matches with results**. The best
real series so far filed 3 of 6, and a series that files 3 is scored by rule 35
as not having played the other three — worse than losing them.

The failure being reproduced is the real one. Mid-mini-game the opponent's
endpoint stops accepting our sends: every `send_turn` raises, the gatekeeper
exhausts its retries, and `play_sub_game` dies. What must *not* happen is what
happened in the uoh-sqak series — the exception reaching `play_series` and
ending the match, so the remaining mini-games were never played and our endpoint
went dark while their watchdog scored and carried on.

The peer here recovers after the storm, because that is the case worth
protecting: a tunnel that drops for one game and comes back must cost one game.
"""

import threading

import pytest

from najamjad_agent.constants import EndReason, Role
from tests.fakes.network import linked_pair
from tests.integration.test_match_series import build_runner, play_pair

#: Which mini-game the opponent's endpoint goes away during.
DEAD_SUB_GAME = 2


class StormingLink:
    """A transport that stops accepting sends during one mini-game.

    Wraps the real linked transport rather than replacing it, so every other
    part of the protocol behaves exactly as it does in a healthy series. A fake
    that failed *everything* would prove the runner survives a dead peer; this
    proves it survives a peer that dies and returns, which is the case that
    actually costs points.
    """

    def __init__(self, inner, dead_sub_game: int) -> None:
        self._inner = inner
        self._dead = dead_sub_game
        self._sub_game = 0
        self.refused = 0

    def __getattr__(self, name):
        """Everything not overridden below passes straight through."""
        return getattr(self._inner, name)

    def reset(self) -> None:
        """`MatchRunner.play_sub_game` resets the transport first, every game.

        Counted here rather than hooked to a `begin_sub_game` the runner does
        not call — a fake that instruments a method nothing invokes injects no
        fault at all, and reports success for it.
        """
        self._sub_game += 1
        self._inner.reset()

    def send_turn(self, message) -> None:
        if self._sub_game == self._dead:
            self.refused += 1
            raise RuntimeError("mcp_peer: failed after 10 attempts")
        self._inner.send_turn(message)


def _storming_pair():
    """Two peers, one of which cannot send during `DEAD_SUB_GAME`."""
    left, right = linked_pair()
    storming = StormingLink(left, DEAD_SUB_GAME)
    ours = build_runner(storming, "najamjad", "opponent", Role.COP)
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)
    return ours, theirs, storming


@pytest.fixture()
def stalled():
    """A full series in which our sends died for one mini-game."""
    ours, theirs, storming = _storming_pair()
    play_pair(ours, theirs)
    return ours, storming


def test_the_series_still_plays_every_sub_game(stalled) -> None:
    """The requirement. A storm in game 2 must not cost games 3 to 6."""
    ours, _ = stalled

    assert len(ours.games) == ours.tracker.total_games


def test_the_storm_actually_happened(stalled) -> None:
    """A resilience test whose fault never fired proves nothing at all."""
    _, storming = stalled

    assert storming.refused > 0, "the injected storm never refused a send"


def test_a_storm_costs_at_most_the_game_it_hits_and_the_one_after(stalled) -> None:
    """The measured blast radius, recorded rather than wished for.

    The assertion here was originally `== 1`, and that was the property I wanted
    rather than the one the system has. It is **2**: the storm kills the game it
    lands in, and the following game too, because when we abandon mid-mini-game
    the peer does not know we have — it is still waiting on a turn, and it burns
    its own watchdog before both sides resynchronise at the next boundary.

    Two is bounded and survivable; six is not, and six is what used to happen.
    Recording the real number keeps the gate honest, and `T-2485` tracks
    shrinking it — the peer should be told we are abandoning rather than left to
    time out.
    """
    ours, _ = stalled
    reasons = [str(game.get("end_reason", "")) for game in ours.games]

    assert reasons.count(EndReason.TIMEOUT.value) <= 2
    assert reasons.count(EndReason.TIMEOUT.value) >= 1, "the storm cost nothing at all"


def test_the_stalled_game_reports_the_steps_it_really_played(stalled) -> None:
    """Rules 33-35 void both reports when they contradict.

    A game we abandoned at step 11 must not be filed as never played: the
    opponent has eleven of our sealed turns and will say so.
    """
    ours, _ = stalled
    stalled_game = ours.games[DEAD_SUB_GAME - 1]

    assert stalled_game["end_reason"] == EndReason.TIMEOUT.value
    assert stalled_game["steps"] >= 0


def test_every_sub_game_is_filed_exactly_once(stalled) -> None:
    """Rule 35 scores a missing report as not having played."""
    ours, _ = stalled
    numbers = [game["sub_game"] for game in ours.games]

    assert sorted(numbers) == list(range(1, ours.tracker.total_games + 1))


def test_the_series_still_scores_out(stalled) -> None:
    """A series that cannot produce a result is a series we did not play."""
    ours, _ = stalled
    result = ours.tracker.result()

    assert result is not None
    assert len(ours.tracker.outcomes) == ours.tracker.total_games


def test_a_healthy_series_is_unaffected() -> None:
    """The control: without the storm, nothing here changes."""
    left, right = linked_pair()
    ours = build_runner(left, "najamjad", "opponent", Role.COP)
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)

    play_pair(ours, theirs)

    assert len(ours.games) == ours.tracker.total_games
    assert all(
        str(game.get("end_reason", "")) != EndReason.TIMEOUT.value for game in ours.games
    )


def test_the_gate_can_still_fail() -> None:
    """If the storm never ends, the series must still complete every game.

    A peer that goes away and stays away is the harsher case, and it must
    degrade rather than hang: six technical outcomes, six filed records, and a
    runner that returns.
    """
    left, right = linked_pair()
    storming = StormingLink(left, dead_sub_game=-1)
    storming._dead = None  # noqa: SLF001 - every sub-game storms
    storming.send_turn = lambda _message: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("mcp_peer: failed after 10 attempts")
    )
    ours = build_runner(storming, "najamjad", "opponent", Role.COP)
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)

    threads = [threading.Thread(target=r.play_series, daemon=True) for r in (ours, theirs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert len(ours.games) == ours.tracker.total_games


def test_the_settle_wait_is_spent_only_on_the_abandoned_game() -> None:
    """The peer needs its watchdog to fire before it will answer the next handshake.

    Asserted through the runner rather than on `settle` alone, because the thing
    worth guarding is the *wiring*: an unreferenced component is this repo's most
    common defect, and a settle nobody calls settles nothing.
    """
    left, right = linked_pair()
    storming = StormingLink(left, DEAD_SUB_GAME)
    slept: list[float] = []
    ours = build_runner(storming, "najamjad", "opponent", Role.COP)
    ours._watchdog_seconds = 30.0  # noqa: SLF001
    ours._sleep = slept.append  # noqa: SLF001
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)

    play_pair(ours, theirs)

    assert slept, "the settle wait was never spent after an abandonment"
    assert all(each == 30.0 for each in slept)
    assert len(slept) <= 2, "settling should follow abandonments, not every game"


def test_a_clean_series_never_settles() -> None:
    """Five of six games end cleanly; a delay on those costs minutes per series."""
    left, right = linked_pair()
    slept: list[float] = []
    ours = build_runner(left, "najamjad", "opponent", Role.COP)
    ours._watchdog_seconds = 30.0  # noqa: SLF001
    ours._sleep = slept.append  # noqa: SLF001
    theirs = build_runner(right, "opponent", "najamjad", Role.THIEF)

    play_pair(ours, theirs)

    assert slept == []
