"""Does the opponent expose a surface we can actually play against? (T-2444)

Split from `preflight_checks` because that module reached its line budget and
the rule there is explicit that splitting beats compressing. Coherent on its
own: every other check inspects *our* machine, this one inspects theirs.

The gap it closes: one opponent's agent exposed a single non-spec tool,
`receive_move`, and it took three failed matches to discover. Every check we had
passed — the URL was configured, the endpoint answered, the tunnel was up — and
none of them asked whether there was anything there we could call.
"""

from collections.abc import Callable
from typing import Any

#: The four tools every league peer must expose (ADR-001, reference contract).
MANDATED_TOOLS = ("negotiate", "receive_turn", "submit_audit", "receive_control")


def opponent_tools_check(
    opponent_url: str, lister: Callable[[str], Any] | None = None
) -> Callable[[], str]:
    """Confirm the peer exposes the four tools a match is played through.

    `answers_http` is necessary and not sufficient: a tunnel edge answers while
    the agent behind it is dead, and an agent answers while exposing a surface
    we cannot play against.

    A superset passes — their extra tools are their business. `lister` is
    injectable for the same reason `gmail_check`'s loader is: a verdict that
    depends on whether some opponent happens to be online proves nothing about
    the code, and would fail in CI where nobody is.
    """

    def probe() -> str:
        """List the peer's tools and insist the four mandated ones are present."""
        if not str(opponent_url or "").strip():
            # `opponent_url` already reports this gap; two checks failing for
            # one cause reads to an operator as two separate problems.
            return "no opponent configured yet — nothing to inspect"
        call = lister
        if call is None:
            from .mcp_probe import list_tools as call
        exposed = {str(name) for name in call(opponent_url)}
        missing = [tool for tool in MANDATED_TOOLS if tool not in exposed]
        if missing:
            raise ValueError(
                f"opponent exposes {sorted(exposed) or 'nothing'}; "
                f"a match needs all of {list(MANDATED_TOOLS)} — missing {missing}"
            )
        return f"all {len(MANDATED_TOOLS)} mandated tools present"

    return probe
