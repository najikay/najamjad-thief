"""Is the opponent's MCP server actually up? — asked before we commit to play.

Part of the egress path, split from `mcp_client` because that module reached
its line budget and the rule there is explicit that splitting beats
compressing. It shares the client's privilege of speaking to the opponent
directly, and the architecture test names it alongside the others.

The distinction it exists to make: a tunnel edge accepts TCP whether or not
the agent behind it is running. Only an HTTP response tells them apart.
"""

from __future__ import annotations


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
