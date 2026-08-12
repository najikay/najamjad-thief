"""One outbound call must not be allowed to consume the whole signed deadline.

The MCP SDK's own per-call default is 30 s, which is exactly the response
timeout we sign. So a push that is delivered but never answered, plus a backoff
and one retry, is past 30 s — we breach terms we agreed to, and no single call
in the log looks slow enough to blame. imreeyal lost two sub-games to this and
wrote up the arithmetic.

The cap therefore has to be *strictly* under the deadline, and a config that
does not satisfy that is refused at build time rather than discovered live.
"""

from __future__ import annotations

from typing import Any

import pytest

from najamjad_agent.sdk.match_setup import build_transport


class _Bus:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class _Manager:
    """Just the config lookups `build_transport` performs."""

    def __init__(self, **overrides: Any) -> None:
        self._values: dict[str, Any] = {
            "network.response_timeout_seconds": 30,
            "network.call_timeout_seconds": 10,
            "network.max_retries": 3,
            "paths.rate_limits": "config/rate_limits.json",
        }
        self._values.update(overrides)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def require(self, key: str) -> Any:
        if key == "network.opponent_url":
            return "https://opponent.example.com/mcp"
        return self._values[key]


def test_the_configured_cap_reaches_the_client() -> None:
    """The gap was never the value, it was that nothing passed it.

    `PeerClient` took `call_timeout` from the day it was written and
    `build_transport` never supplied it, so the 30 s default is what every match
    actually ran on.
    """
    transport = build_transport(_Manager(), _Bus(), inboxes=object())

    assert transport.client._timeout == 10.0


def test_a_cap_at_or_above_the_deadline_is_refused() -> None:
    """Equal is not under: a retry has to fit inside the deadline too."""
    for cap in (30, 31, 60):
        with pytest.raises(ValueError, match="strictly under"):
            build_transport(
                _Manager(**{"network.call_timeout_seconds": cap}), _Bus(), inboxes=object()
            )


def test_raising_the_signed_deadline_raises_the_ceiling_with_it() -> None:
    """Rule 12 lets a term be raised, so the guard is relative, not a literal 10."""
    transport = build_transport(
        _Manager(**{"network.response_timeout_seconds": 60,
                    "network.call_timeout_seconds": 45}),
        _Bus(), inboxes=object(),
    )

    assert transport.client._timeout == 45.0


def test_the_client_default_is_also_under_the_reference_deadline() -> None:
    """A directly-constructed client must not be the one place that still breaches."""
    from najamjad_agent.net.mcp_client import PeerClient

    client = PeerClient(opponent_url="https://x.example/mcp", gatekeeper=None)

    assert client._timeout < 30.0
