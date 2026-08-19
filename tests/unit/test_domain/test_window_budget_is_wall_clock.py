"""The bound we quote an opponent has to be the bound we keep.

We told anrbj666 in writing that our per-window patience was "16.7 minutes",
derived as `BUSY_RETRIES x BUSY_BACKOFF_SECONDS`. That arithmetic counts only
the sleep between attempts and ignores what an attempt itself costs: against an
unreachable door the gatekeeper spends its full deadline first, about 100 s. So
the real bound was nearer three hours, and on 2026-08-19 a cop process sat in
that loop for fourteen minutes before being stopped by hand.

Attempt counting cannot express "wait one opponent window" at all, because the
price of an attempt depends on how the peer fails — a refusal returns in
milliseconds, a dead door in a hundred seconds. Wall clock is what we meant.
"""


from najamjad_agent.domain.handshake_retry import (
    BUSY_RETRIES,
    WINDOW_BUDGET_SECONDS,
    agree_on_terms,
)


class _Clock:
    """A clock the test advances by hand, so no test waits on real time."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _busy() -> None:
    from najamjad_agent.negotiation.handshake import HandshakeBusyError

    raise HandshakeBusyError("a mini-game is in progress")


def test_an_expensive_attempt_still_ends_the_window_on_time() -> None:
    """The defect: each attempt burned ~100 s that the budget never counted."""
    clock, events = _Clock(), []

    def costly(_seconds: float) -> None:
        clock.now += 110.0          # the sleep, plus a failing call

    assert not agree_on_terms(_busy, sub_game=4, retries=2, emit=events.append,
                              sleep=costly, clock=clock)

    assert clock.now <= WINDOW_BUDGET_SECONDS + 110.0, "overran its own bound"
    attempts = [e for e in events if e["event"] == "handshake.waiting_for_window"]
    assert len(attempts) < BUSY_RETRIES, "gave up on wall clock, not on attempts"
    assert events[-1]["event"] == "handshake.exhausted"


def test_cheap_attempts_still_get_the_full_attempt_budget() -> None:
    """A peer refusing in milliseconds is healthy, and must not be cut short by
    a clock that has barely moved."""
    clock, events = _Clock(), []

    def instant(_seconds: float) -> None:
        clock.now += 0.001

    assert not agree_on_terms(_busy, sub_game=4, retries=2, emit=events.append,
                              sleep=instant, clock=clock)

    waited = [e for e in events if e["event"] == "handshake.waiting_for_window"]
    assert len(waited) == BUSY_RETRIES, "the attempt cap is what should bite here"


def test_a_peer_that_recovers_inside_the_budget_is_played() -> None:
    """The budget exists to bound failure, never to abandon a working peer."""
    clock, calls = _Clock(), {"n": 0}

    def busy_then_fine() -> None:
        calls["n"] += 1
        if calls["n"] <= 3:
            _busy()

    def costly(_seconds: float) -> None:
        clock.now += 110.0

    assert agree_on_terms(busy_then_fine, sub_game=4, retries=2,
                          emit=lambda _e: None, sleep=costly, clock=clock)


def test_the_default_clock_needs_no_wiring() -> None:
    """Every existing caller passes neither clock nor sleep."""
    assert agree_on_terms(lambda: None, sub_game=1, retries=2, emit=lambda _e: None)


def test_the_quoted_number_is_the_one_we_keep() -> None:
    """16.7 minutes is what anrbj666 was told; it must stay true by construction."""
    assert WINDOW_BUDGET_SECONDS / 60 == 1000.0 / 60
    assert 16.0 <= WINDOW_BUDGET_SECONDS / 60 <= 17.0
