"""Does the public hostname actually have our agent behind it?

Split from `preflight_checks` when that file crossed its budget, and it earns a
module: this is the one check that leaves the machine, and it is the one that
was quietly lying.

It used to `return tunnel.public_url` — the configured string, echoed back —
under a docstring claiming it confirmed a live endpoint, while
`docs/runbook-network.md` claimed preflight performed "a self-call through the
public URL". Neither was true. So the checklist printed `PASS` for a hostname
with nothing behind it, which is precisely the trap that runbook warns about in
bold ("a running tunnel proves nothing about the agent"), served back as
reassurance.

There is a `check_tunnel_self_call` in `preflight.py` that does this properly
and has never had a production caller.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def tunnel_check(tunnel: Any) -> Callable[[], Any]:
    """Ask the public hostname what is behind it, and report only what it said.

    Three outcomes, because they need three different responses from an
    operator and only one of them is a red line:

    * **the origin answered** — real evidence, and the only state that is proof;
    * **an edge failure (502/530)** — DNS and the tunnel edge exist, nothing is
      serving behind them. That is the *expected* state before the agent is
      started, which is exactly when preflight is designed to run: `port_check`
      passes only while the port is still free. Blocking here would make the
      tool contradict its own documented sequence, so it does not — but it
      refuses to call the result proof;
    * **nothing answered at all** — a missing DNS route or no such host, which
      starting the agent will not fix. A genuine red.

    Returning `None` when no tunnel is configured stays the honest answer: local
    play is a legitimate setup, not a failure.
    """

    def probe() -> Any:
        """Report what the public hostname actually answered."""
        url = str(getattr(tunnel, "public_url", "") or "") if tunnel is not None else ""
        if not url:
            return None
        from .http_probe import probe as http_probe

        result = http_probe(url)
        if result.origin_alive:
            return f"our server answered through {url} (HTTP {result.status})"
        if not result.reached:
            raise RuntimeError(
                f"{url} could not be reached ({result.error}) — a missing DNS route "
                "is not fixed by starting the agent; re-run `cloudflared tunnel route dns`"
            )
        return (
            f"{url} resolves but nothing is serving it (HTTP {result.status}) — "
            "NOT proof of reachability. Start the agent and the tunnel, then curl "
            "it yourself before the T."
        )

    return probe
