"""Preflight must see the opponent's tool surface, not just their door (T-2444).

One opponent's agent exposed a single non-spec tool, `receive_move`, and it took
**three failed matches** to find out. Every check we had passed: the URL was
configured, the endpoint answered, the tunnel was up. None of them asked the one
question that decides whether a match can happen — does the peer expose the four
tools the book mandates?

`answers_http` is not enough. A tunnel edge answers while the agent behind it is
dead, and an agent answers while exposing nothing we can call.

The lister is injectable for the same reason `gmail_check`'s loader is: a check
whose verdict depends on whether some opponent happens to be online right now
proves nothing about the code, and would fail in CI where nobody is.
"""

import pytest

from najamjad_agent.net.preflight_opponent import opponent_tools_check

MANDATED = ("negotiate", "receive_turn", "submit_audit", "receive_control")


def test_all_four_mandated_tools_pass() -> None:
    probe = opponent_tools_check("https://peer/mcp", lister=lambda _url: list(MANDATED))

    assert "4" in probe() or "negotiate" in probe()


def test_extra_tools_are_not_a_failure() -> None:
    """Their surface is theirs; we require a superset, never an exact match."""
    probe = opponent_tools_check(
        "https://peer/mcp", lister=lambda _url: [*MANDATED, "their_own_extra"]
    )

    probe()


def test_the_receive_move_opponent_is_caught() -> None:
    """The real case: one non-spec tool, three matches lost before we knew."""
    probe = opponent_tools_check("https://peer/mcp", lister=lambda _url: ["receive_move"])

    with pytest.raises(ValueError) as failure:
        probe()

    message = str(failure.value)
    for tool in MANDATED:
        assert tool in message, f"the operator needs to see {tool} named"


def test_one_missing_tool_is_named() -> None:
    """Naming which one is missing is the difference between a fix and a guess."""
    probe = opponent_tools_check(
        "https://peer/mcp", lister=lambda _url: [t for t in MANDATED if t != "submit_audit"]
    )

    with pytest.raises(ValueError, match="submit_audit"):
        probe()


def test_an_unreachable_opponent_fails_the_check() -> None:
    """Cannot ask means cannot confirm — never a silent pass."""

    def _unreachable(_url: str):
        raise OSError("connection refused")

    probe = opponent_tools_check("https://peer/mcp", lister=_unreachable)

    with pytest.raises(OSError):
        probe()


def test_no_opponent_url_is_not_a_tool_failure() -> None:
    """Before negotiation there is no peer to inspect; `opponent_url` reports
    that gap already, and two checks failing for one cause reads as two."""
    probe = opponent_tools_check("", lister=lambda _url: [])

    assert "no opponent" in probe().lower()
