"""Tests for naming a fault whose exception refuses to name itself.

Every case here is taken from the real event log of the uoh-sqak series, where
152 of 154 connect failures recorded `Client failed to connect: ` and nothing
else. These tests exist so that log can never be written again.
"""

import builtins

import httpx
import pytest

from najamjad_agent.shared.error_detail import cause_chain, describe, leaves, message

#: The builtin only exists from 3.11 and `pyproject` allows 3.10, so it is
#: fetched rather than named — and `leaves` duck-types on `.exceptions` for the
#: same reason plus a better one: anyio ships its own group class, which is what
#: actually reaches us from a failing task group and is not the builtin at all.
_BUILTIN_GROUP = getattr(builtins, "BaseExceptionGroup", None)


class TaskGroupError(Exception):
    """A group shaped like anyio's, which is the shape the production code sees.

    Not a stand-in for the builtin — a stand-in for the thing we actually get.
    Testing only against `BaseExceptionGroup` would prove the code handles a
    class it never meets in a match.
    """

    def __init__(self, message: str, exceptions: tuple[BaseException, ...]) -> None:
        super().__init__(message)
        self.exceptions = tuple(exceptions)


def test_an_empty_message_falls_back_to_repr() -> None:
    """The exact failure that made 152 log lines say nothing at all."""
    assert message(httpx.ConnectError("")) == "ConnectError('')"


def test_a_real_message_is_preferred_over_repr() -> None:
    assert message(ValueError("cell out of bounds")) == "cell out of bounds"


def test_whitespace_only_messages_count_as_empty() -> None:
    """`RuntimeError('Client failed to connect: ')` trails a space, so strip."""
    assert message(RuntimeError("   ")).startswith("RuntimeError(")


def test_an_ordinary_exception_is_its_own_only_leaf() -> None:
    error = ValueError("plain")
    assert leaves(error) == (error,)


def test_a_group_is_unwrapped_to_the_exceptions_inside_it() -> None:
    """anyio raises a group whenever a task group unwinds; the group says nothing."""
    inner = (httpx.ConnectError(""), OSError("connection refused"))
    found = leaves(TaskGroupError("unhandled errors in a TaskGroup", inner))
    assert [type(each).__name__ for each in found] == ["ConnectError", "OSError"]


def test_nested_groups_are_flattened_completely() -> None:
    deep = TaskGroupError("outer", (TaskGroupError("inner", (ValueError("x"),)),))
    assert [str(each) for each in leaves(deep)] == ["x"]


@pytest.mark.skipif(_BUILTIN_GROUP is None, reason="ExceptionGroup landed in 3.11")
def test_the_builtin_exception_group_is_unwrapped_too() -> None:
    """The duck-type must also cover the real thing where the runtime has it."""
    group = _BUILTIN_GROUP("tg", [httpx.ConnectError(""), OSError("refused")])  # type: ignore[misc]
    assert [type(each).__name__ for each in leaves(group)] == ["ConnectError", "OSError"]


def test_the_cause_chain_reaches_the_exception_that_started_it() -> None:
    """fastmcp -> httpx -> OSError is the chain the log never followed."""
    try:
        try:
            raise OSError("connection refused")
        except OSError as root:
            raise httpx.ConnectError("") from root
    except httpx.ConnectError as wrapper:
        chain = cause_chain(wrapper)
    assert "connection refused" in chain
    assert chain.startswith("ConnectError:")


def test_the_cause_chain_is_bounded_so_a_long_stack_cannot_flood_the_log() -> None:
    error: BaseException = ValueError("root")
    for depth in range(10):
        error = ValueError(f"wrap-{depth}").with_traceback(None)
        error.__cause__ = ValueError("root")
    assert cause_chain(error).count(" <- ") <= 3


def test_a_self_referencing_cause_terminates() -> None:
    """A cycle must end the walk, not hang the game loop that is logging it."""
    error = ValueError("loop")
    error.__cause__ = error
    assert cause_chain(error) == "ValueError: loop"


def test_describe_keeps_the_field_names_the_existing_events_use() -> None:
    """Dashboards and notebooks filter on `error`/`detail`; both must survive."""
    described = describe(ValueError("boom"))
    assert described["error"] == "ValueError"
    assert described["detail"] == "boom"


def test_describe_names_the_cause_of_an_empty_wrapper() -> None:
    """The whole point: an empty `detail` must still yield a usable `cause`."""
    try:
        try:
            raise OSError("[Errno 111] Connection refused")
        except OSError as root:
            raise RuntimeError("Client failed to connect: ") from root
    except RuntimeError as wrapper:
        described = describe(wrapper)
    assert described["detail"] == "Client failed to connect:"
    assert "Connection refused" in described["cause"]


def test_describe_reports_how_many_exceptions_a_group_carried() -> None:
    group = TaskGroupError("tg", (httpx.ConnectError(""), httpx.ConnectError("")))
    described = describe(group)
    assert described["grouped"] == ["ConnectError", "ConnectError"]


def test_describe_omits_the_group_field_for_a_single_exception() -> None:
    assert "grouped" not in describe(ValueError("solo"))


@pytest.mark.parametrize("limit", [10, 50])
def test_every_field_honours_the_truncation_limit(limit: int) -> None:
    """A tunnel edge can return a whole HTML page as its `str()`."""
    described = describe(ValueError("x" * 5000), limit=limit)
    assert len(described["detail"]) <= limit
    assert len(described["cause"]) <= limit
