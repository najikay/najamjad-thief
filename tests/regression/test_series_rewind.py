"""The 2026-08-21 anrbj666 desync, replayed: ours at 5, theirs at 3, both dying.

The shape from the event log: our side times a dead window out and advances;
theirs re-offers it forever. From then on every negotiate either side sends
names a window the other refuses — 63 refusals at our door, their window-3
greetings dropped as `handshake.window_mismatch` at ours — and two windows
clock out at step 0 having exchanged nothing.

The cure has three parts, pinned here end to end: a mismatched negotiate is
**held** keyed by the window it names instead of dropped; a busy-wait aborts
early once a held window proves the peer is *behind* us rather than not ready
(`handshake.peer_is_behind`); and the series then **rewinds** to that window,
popping only step-0 technicals, so both reports end up carrying the same real
game under the same number. Convergence is part of the pin: a window rewinds
at most once, stale holds are purged, and the series still ends.
"""

from __future__ import annotations

from najamjad_agent.constants import EndReason, Move, Role
from najamjad_agent.domain.handshake_retry import agree_on_terms
from najamjad_agent.domain.match import MatchRunner
from najamjad_agent.domain.scoring import ScoreTable
from najamjad_agent.domain.series import SeriesTracker
from najamjad_agent.negotiation.handshake import HandshakeBusyError
from tests.fakes.orchestration import FixedSpeaker, ScriptedBrain, build_state
from tests.integration.test_headless_game import SCORING


class Quiet:
    """A transport nobody is behind."""

    def send_turn(self, message): ...
    def reset(self, sub_game: int = 0): ...
    def new_session(self): ...
    def finish_sub_game(self): ...
    def send_audit(self, payload): ...

    def receive_turn(self, timeout):
        return None

    def receive_audit(self, timeout):
        return None


class LeapingClock:
    """Monotonic time that leaps, so wall-clock budgets spend in two calls."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 600.0
        return self.now


class DesyncedPeer:
    """A peer stuck on window 3 while we are past it.

    Windows 1 and 2 agree normally. Window 3 never agrees on its own — their
    process is wedged mid-boundary — but once we are at window 4+, their
    window-3 negotiates keep arriving and are held. The seeded window 3 then
    agrees instantly, which is exactly what the held agreement is for.
    """

    def __init__(self) -> None:
        self.held_agreements: dict[int, dict] = {}

    def __call__(self, role: str = "", sub_game: int = 0) -> dict:
        if sub_game <= 2:
            return {"terms": {}}
        if sub_game == 3 and self.held_agreements.get(3):
            return {"terms": {}}
        if sub_game >= 4:
            self.held_agreements[3] = {"sub_game_number": 3}
        raise HandshakeBusyError("a mini-game is in progress")


def build_runner(handshake) -> tuple[MatchRunner, list[dict]]:
    events: list[dict] = []
    runner = MatchRunner(
        params=build_state(Role.COP).board.params,
        tracker=SeriesTracker("us", "them", ScoreTable.from_config(SCORING), Role.COP, 6),
        transport=Quiet(),
        build_state=lambda _p, role, _sg: build_state(role),
        build_brain=lambda _role, _state: ScriptedBrain([Move.STAY] * 200),
        speaker=FixedSpeaker(),
        clock=LeapingClock(),
        handshake=handshake,
        handshake_retries=1,
        response_timeout=0.001,
        max_retries=1,
        audit_timeout=0.001,
        emit=events.append,
        sleep=lambda _s: None,
    )
    return runner, events


def test_the_series_rewinds_to_the_window_the_peer_still_holds() -> None:
    runner, events = build_runner(DesyncedPeer())

    runner.play_series()

    names = [e.get("event") for e in events]
    assert "handshake.peer_is_behind" in names, "the busy-wait must abort early"
    rewinds = [e for e in events if e.get("event") == "series.rewound"]
    assert [(e["to"]) for e in rewinds] == [3], "exactly one rewind, to window 3"

    played_3 = [o for o in runner.tracker.outcomes if o.sub_game == 3]
    assert len(played_3) == 1, "one window 3 in the ledger, never two"
    assert played_3[0].end_reason is not EndReason.OPPONENT_QUIT, (
        "the rewound window must be the real game, not the popped technical"
    )
    assert len([g for g in runner.games if g.get("sub_game") == 3]) == 1
    assert runner.tracker.is_complete, "and the series still ends"


def test_a_real_result_is_never_popped() -> None:
    tracker = SeriesTracker("us", "them", ScoreTable.from_config(SCORING), Role.COP, 6)
    tracker.record(end_reason=EndReason.CAPTURE, role=Role.COP, steps=12)
    tracker.record(end_reason=EndReason.TIMEOUT, role=Role.THIEF, steps=0)

    assert tracker.rewind_to(1) is False, "a played game is evidence"
    assert tracker.rewind_to(2) is True, "a step-0 technical is not"
    assert tracker.cursor == 1 and len(tracker.outcomes) == 1


def test_a_technical_with_steps_played_blocks_the_rewind() -> None:
    tracker = SeriesTracker("us", "them", ScoreTable.from_config(SCORING), Role.COP, 6)
    tracker.record(end_reason=EndReason.TIMEOUT, role=Role.COP, steps=11)

    assert tracker.rewind_to(1) is False, (
        "eleven sealed turns exist on both sides; replaying that number would "
        "put two different games under it (rules 33-35)"
    )


def test_waiting_continues_when_nothing_is_held() -> None:
    """The early abort must not fire on an empty holder — the sixteen-minute
    patience for a slow-spawning peer is itself a fix that cost a series."""

    def busy(role: str = "", sub_game: int = 0):
        raise HandshakeBusyError("a mini-game is in progress")

    busy.held_agreements = {}
    events: list[dict] = []
    clock = LeapingClock()

    agreed = agree_on_terms(busy, 4, 1, events.append, sleep=lambda _s: None, clock=clock)

    assert agreed is False
    names = [e.get("event") for e in events]
    assert "handshake.peer_is_behind" not in names
    assert "handshake.waiting_for_window" in names or "handshake.exhausted" in names
