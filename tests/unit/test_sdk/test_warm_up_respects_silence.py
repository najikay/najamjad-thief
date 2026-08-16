"""A run that will never speak must not pay to warm the voice.

`_apply_emission` promises that `hint = false` "skips the vendor call outright,
so a silent run is genuinely free: zero tokens, no provider latency". The
warm-up was called unconditionally at bootstrap, which made that promise false.

Measured on the 2026-08-14 vibecode friendly, played with `--no-hints`: two
`llm.completion` events, **97 tokens each**, and 42 seconds between `llm.warm_up`
and `llm.warmed` — spent warming a provider that no turn in the series would
ever call. It also wrote 97 into our step-0 running total while our own result
artifact reported `tokens_total_series: 0`, so our two files disagreed about our
own spend and theirs reported 97 where ours said 0.

The warm-up itself stays and is worth its cost when hints are on: a cold DeepSeek
call takes 27-61 s against a 30 s turn budget, and paying that inside game 1 once
cost 153 seconds.
"""

from __future__ import annotations

from typing import Any

from najamjad_agent.llm.warm_up import warm_up


class Router:
    """A router that records whether anybody asked it for a completion."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs: Any) -> str:
        self.calls += 1
        return "ready"


def _bootstrap_decision(hints_on: bool) -> tuple[int, list[dict]]:
    """The bootstrap branch, exercised with the real `warm_up`."""
    router, events = Router(), []
    if hints_on:
        warm_up(router, emit=events.append)
    else:
        events.append({"event": "llm.warm_up_skipped", "reason": "hints are off this run"})
    return router.calls, events


def test_a_hint_free_run_makes_no_vendor_call() -> None:
    """The regression: 97 tokens and 42 seconds for a call that cannot happen."""
    calls, events = _bootstrap_decision(hints_on=False)

    assert calls == 0
    assert [event["event"] for event in events] == ["llm.warm_up_skipped"]


def test_a_talking_run_still_warms_up() -> None:
    """The cold-start cost is real and must keep being paid before game 1."""
    calls, events = _bootstrap_decision(hints_on=True)

    assert calls == 1
    assert [event["event"] for event in events] == ["llm.warm_up", "llm.warmed"]


def test_skipping_is_announced_rather_than_silent() -> None:
    """Silence here would read as a warm router.

    `warm_up`'s own docstring makes the point about failure — "silence reads as
    a warm router, and the next sixty-second turn arrives as a surprise during a
    game rather than as a warning before one". Not warming at all deserves the
    same treatment: an operator reading the log must be able to tell "we skipped
    it deliberately" from "it never ran".
    """
    _, events = _bootstrap_decision(hints_on=False)

    assert events[0]["reason"]
