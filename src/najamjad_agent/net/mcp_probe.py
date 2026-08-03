"""Is the opponent's MCP server actually up? — asked before we commit to play.

Part of the egress path, split from `mcp_client` because that module reached
its line budget and the rule there is explicit that splitting beats
compressing. It shares the client's privilege of speaking to the opponent
directly, and the architecture test names it alongside the others.

The distinction it exists to make: a tunnel edge accepts TCP whether or not
the agent behind it is running. Only an HTTP response tells them apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _run_isolated(build: Callable[[], Any], timeout: float) -> Any:
    """Run one coroutine to completion, whether or not a loop is already running.

    `asyncio.run` refuses to nest, and preflight has two callers with different
    answers to "are we inside a loop": the CLI is not, the dashboard is —
    `/api/cockpit` is an async endpoint, so `sdk.cockpit()` runs on the server's
    running loop. There, `asyncio.run` raised `RuntimeError` and left the
    coroutine unawaited, which `run_check` dutifully reported as a *failed*
    check while the same check passed from the CLI, and every unawaited
    coroutine added a `RuntimeWarning` to the terminal until it scrolled.

    A dedicated thread with its own loop is the answer rather than
    `loop.run_until_complete`: this is a blocking call by contract, its callers
    are synchronous, and borrowing the server's loop would deadlock the very
    request that is waiting on it.
    """
    import asyncio
    import threading

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(build(), timeout=timeout))

    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["value"] = asyncio.run(asyncio.wait_for(build(), timeout=timeout))
        except BaseException as error:  # noqa: BLE001 - re-raised in the caller's thread
            outcome["error"] = error

    thread = threading.Thread(target=worker, name="mcp-probe", daemon=True)
    thread.start()
    # Generous: the coroutine has its own `timeout`, and this only has to
    # outlast it plus the thread's own start-up and teardown.
    thread.join(timeout=timeout + 5.0)
    if "error" in outcome:
        raise outcome["error"]
    if "value" not in outcome:
        raise TimeoutError(f"probe did not finish within {timeout + 5.0:.0f}s")
    return outcome["value"]


def list_tools(url: str, timeout: float = 10.0) -> list[str]:
    """The tool names the opponent's MCP server exposes.

    A real MCP session, unlike `endpoint_answers` — the tool list is only
    available after initialisation, and the question here is what we can
    actually call rather than whether anyone is home. Asked once at preflight,
    so the session cost that rules it out for polling is irrelevant.

    Raises rather than returning empty on failure: "we could not ask" and "they
    expose nothing" are different answers, and a preflight that reports the
    second when it means the first sends an operator to fix the wrong machine.
    """
    from fastmcp import Client

    async def _ask() -> list[str]:
        async with Client(url) as client:
            return [str(getattr(tool, "name", tool)) for tool in await client.list_tools()]

    return _run_isolated(_ask, timeout)


def list_tools(url: str, timeout: float = 10.0) -> list[str]:
    """The tool names the opponent's MCP server exposes.

    A real MCP session, unlike `endpoint_answers` — the tool list is only
    available after initialisation, and the question here is what we can
    actually call rather than whether anyone is home. Asked once at preflight,
    so the session cost that rules it out for polling is irrelevant.

    Raises rather than returning empty on failure: "we could not ask" and "they
    expose nothing" are different answers, and a preflight that reports the
    second when it means the first sends an operator to fix the wrong machine.
    """
    import asyncio

    from fastmcp import Client

    async def _ask() -> list[str]:
        async with Client(url) as client:
            return [str(getattr(tool, "name", tool)) for tool in await client.list_tools()]

    return asyncio.run(asyncio.wait_for(_ask(), timeout=timeout))


def endpoint_answers(url: str, timeout: float = 5.0) -> bool:
    """Whether an MCP server — not merely a tunnel edge — answers at `url`.

    Here because this module is the single egress path (ADR-009): a readiness
    probe is still traffic we send them, and the architecture test caught the
    first version importing `httpx` from `opponent_wait`.

    No MCP *session* is opened — readiness is polled, and a session per poll
    would leave abandoned sessions on their server. A 4xx counts as ready:
    their server refused us on protocol grounds, so it is up. Only 5xx and
    transport failures mean nobody is home, which is exactly what a live
    tunnel in front of a dead agent returns.
    """
    import httpx

    try:
        response = httpx.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - any transport failure means not ready
        return False
    return response.status_code < 500
