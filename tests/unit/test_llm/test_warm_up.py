"""Pay the cold-start cost before the match, not inside it (T-2433).

Game 1 of a real match took **153 s**; games 2-6 took ~15 s each. A cold
DeepSeek call measures 27-61 s against a 30 s turn deadline.

A timeout was tried and does not help: those calls *succeed*, just slowly, so
nothing fires. The cost is real work — connection setup, TLS, the vendor's own
cold path — and the only way to stop paying it during a turn is to pay it
before the series starts.

The warm-up must never be able to cost a match either. A vendor that is down at
startup is a vendor the router will skip anyway; failing the launch over it
would turn a degraded run into no run at all.
"""

from najamjad_agent.llm.warm_up import warm_up


class Router:
    """Records what the warm-up asked for."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._error = error

    def complete(self, system: str, user: str, max_tokens: int = 200, **kwargs):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        if self._error is not None:
            raise self._error
        return "warm"


def test_the_warm_up_calls_the_router_once() -> None:
    router = Router()

    assert warm_up(router) is True
    assert len(router.calls) == 1


def test_it_asks_for_almost_nothing() -> None:
    """The point is the round trip, not the text — a large generation would
    add the cost it exists to remove, and spend tokens against the series cap."""
    router = Router()

    warm_up(router)

    assert router.calls[0]["max_tokens"] <= 8


def test_a_failing_vendor_does_not_stop_the_launch() -> None:
    """A vendor down at startup is one the router skips anyway. Refusing to
    start would turn a degraded match into no match."""
    router = Router(error=RuntimeError("vendor unavailable"))

    assert warm_up(router) is False
    assert len(router.calls) == 1


def test_it_reports_what_happened() -> None:
    events: list[dict] = []
    warm_up(Router(), emit=events.append)

    assert [event["event"] for event in events] == ["llm.warm_up", "llm.warmed"]


def test_a_failure_is_announced_not_swallowed() -> None:
    """Silence here reads as a warm router, and the next 60 s turn is a surprise."""
    events: list[dict] = []
    warm_up(Router(error=RuntimeError("boom")), emit=events.append)

    names = [event["event"] for event in events]
    assert names == ["llm.warm_up", "llm.warm_up_failed"]
    assert "boom" in str(events[-1])


def test_no_router_is_not_an_error() -> None:
    """Template-only play is a legitimate configuration (book PAGE 67)."""
    assert warm_up(None) is False
