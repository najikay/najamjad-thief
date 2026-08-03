"""The opponent probe has to work from inside a running event loop too (T-2453).

`list_tools` used `asyncio.run`, which refuses to nest. The CLI is not inside a
loop, so preflight passed there; the dashboard is — `/api/cockpit` is an async
endpoint — so the same check raised `RuntimeError`, `run_check` recorded it as a
*failed* check, and the readiness panel disagreed with the terminal. Every
attempt also left the coroutine unawaited, and the `RuntimeWarning`s for those
are what flooded the console.

The suite never caught it because every test called the probe synchronously,
which is the one context where the bug does not exist.
"""

import asyncio
import gc
import warnings

import pytest

from najamjad_agent.net.mcp_probe import _run_isolated


async def answer() -> str:
    await asyncio.sleep(0)
    return "answered"


async def explode() -> str:
    raise ValueError("the peer said no")


async def dawdle() -> str:
    await asyncio.sleep(10)
    return "too late"


def test_it_runs_when_no_loop_is_running() -> None:
    """The CLI path — the one that always worked."""
    assert _run_isolated(answer, timeout=5) == "answered"


@pytest.mark.asyncio
async def test_it_runs_from_inside_a_running_loop() -> None:
    """The dashboard path — the one that raised RuntimeError on every call."""
    assert await asyncio.to_thread(_run_isolated, answer, 5) == "answered"


def test_it_runs_from_inside_a_running_loop_without_a_thread_hop() -> None:
    """Called directly on a live loop, as `sdk.cockpit()` does it."""

    async def caller() -> str:
        return _run_isolated(answer, 5)

    assert asyncio.run(caller()) == "answered"


def test_no_coroutine_is_left_unawaited() -> None:
    """The RuntimeWarning flood was the visible symptom; assert on it directly.

    `gc.collect()` inside the block is load-bearing. "coroutine was never
    awaited" is raised when the object is *collected*, not when it is
    abandoned, so without the collection this test passes against the broken
    code as happily as against the fixed one — which it did, on the first
    attempt at writing it.
    """

    async def caller() -> str:
        return _run_isolated(answer, 5)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        asyncio.run(caller())
        gc.collect()

    unawaited = [item for item in caught if "never awaited" in str(item.message)]
    assert not unawaited, f"leaked coroutines: {[str(w.message) for w in unawaited]}"


def test_the_probe_s_own_failure_reaches_the_caller() -> None:
    """A peer that refuses must fail the check, not be swallowed by the thread."""

    async def caller() -> None:
        _run_isolated(explode, 5)

    with pytest.raises(ValueError, match="the peer said no"):
        asyncio.run(caller())


def test_a_hung_peer_times_out_rather_than_holding_the_dashboard() -> None:
    """Preflight runs while an operator waits; it cannot wait forever."""

    async def caller() -> None:
        _run_isolated(dawdle, 0.2)

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        asyncio.run(caller())
