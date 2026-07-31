"""Pay the vendor's cold-start cost before the series, not during a turn.

Game 1 of a real match took 153 s against games 2-6 at ~15 s each. A cold
DeepSeek call measures 27-61 s, and the turn deadline is 30 s.

A timeout was tried first and does not work, which is the useful part: those
calls *succeed*, just slowly, so no timeout ever fires. The latency is real work
— connection setup, TLS, the vendor's own cold path — and the only way to stop
paying it inside a turn is to pay it before the match begins.

One tiny completion is enough; the point is the round trip, not the text.
"""

from typing import Any

from ..shared.events import Emit

#: Enough to force a real completion, small enough that the warm-up cannot
#: meaningfully spend against the agreed series token budget.
WARM_UP_TOKENS = 8
SYSTEM = "Reply with one word."
USER = "ready"


def warm_up(router: Any, emit: Emit | None = None) -> bool:
    """Make one throwaway completion so the first real hint is not the first call.

    Returns whether a vendor answered. Never raises: a vendor that is down at
    startup is one the router will skip anyway, and refusing to launch over it
    would turn a degraded match into no match at all.

    The failure is announced rather than swallowed, because silence here reads
    as a warm router — and the next sixty-second turn arrives as a surprise
    during a game rather than as a warning before one.
    """
    publish = emit or (lambda _event: None)
    if router is None:
        return False
    publish({"event": "llm.warm_up"})
    try:
        router.complete(system=SYSTEM, user=USER, max_tokens=WARM_UP_TOKENS)
    except Exception as error:  # noqa: BLE001 - reported, never fatal
        publish({"event": "llm.warm_up_failed", "error": f"{type(error).__name__}: {error}"})
        return False
    publish({"event": "llm.warmed"})
    return True
