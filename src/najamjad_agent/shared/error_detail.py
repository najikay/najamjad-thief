"""Naming the fault when the exception refuses to name itself.

152 of 154 connect failures in the uoh-sqak series logged this, in full:

    Client failed to connect:

The message ends at the colon. `str(error)` was empty, so the log recorded the
*type* of the failure a hundred and fifty times and its cause zero times — and
a day was spent arguing about DNS on the strength of the single line that did
carry a message, which turned out to be 1 failure in 154.

An empty `str()` is not a rare accident. It is what you get from:

* `httpx.ConnectError()` raised with no arguments — every first-in-cascade
  failure in that series, and the thing the whole argument was about;
* an `ExceptionGroup`, which anyio raises whenever a task group unwinds: the
  group stringifies to its own label and the exception that matters is inside
  `.exceptions`;
* anything re-raised with `raise ... from cause`, where the cause carries the
  message and the wrapper does not — fastmcp's `RuntimeError` wrapper being
  exactly that shape.

So nothing here trusts `str()`. It falls back to `repr()`, unwraps groups to
their leaves, and follows `__cause__`/`__context__`, because the sentence worth
logging is the one at the bottom of that chain.

Duck-typed on `.exceptions` rather than `isinstance(error, ExceptionGroup)`:
the builtin only exists from 3.11, `pyproject` allows 3.10, and anyio ships its
own backport whose groups would not match the builtin anyway.
"""

from __future__ import annotations

from typing import Any

#: Cap on any single field, so one enormous traceback cannot flood the stream.
MAX_ERROR_DETAIL = 200
#: How deep to follow `__cause__`/`__context__`. Three is past every wrapper we
#: have actually seen (fastmcp -> httpx -> OSError) and stops a cycle dead.
MAX_CAUSE_DEPTH = 3


def message(error: BaseException) -> str:
    """The most informative one-line description of `error` available.

    `str()` first because it is what a library author wrote for a human; `repr()`
    only when `str()` is empty, since `ConnectError()` reads as nothing at all
    while `ConnectError()` at least names itself.
    """
    return str(error).strip() or repr(error)


def leaves(error: BaseException) -> tuple[BaseException, ...]:
    """Flatten an exception group to the real exceptions inside it.

    A group's own message names the group, never the fault. Returns `(error,)`
    unchanged for an ordinary exception, so callers need no special case.
    """
    nested = getattr(error, "exceptions", None)
    if not nested:
        return (error,)
    found: list[BaseException] = []
    for inner in nested:
        found.extend(leaves(inner))
    return tuple(found) or (error,)


def cause_chain(error: BaseException, depth: int = MAX_CAUSE_DEPTH) -> str:
    """Follow `__cause__`/`__context__` down to the exception that started it.

    Rendered as `Wrapper: msg <- Inner: msg`, which is the shape that makes a
    log line answer "what actually failed" without opening a traceback.
    """
    seen: set[int] = set()
    parts: list[str] = []
    current: BaseException | None = error
    while current is not None and len(parts) <= depth and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {message(current)}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)


def describe(error: BaseException, limit: int = MAX_ERROR_DETAIL) -> dict[str, Any]:
    """Event fields naming a failure: its type, its message, and its origin.

    Input: any exception, including a group or a wrapper with an empty message.
    Output: `error` / `detail` / `cause` fields to merge into an event dict.
    Setup: none — pure, so a replayed log describes identically offline.

    `error` and `detail` keep the names the existing events already use, so
    every dashboard filter and every notebook query keeps working; `cause` is
    the new field, and it is the one that would have ended the argument.
    """
    inner = leaves(error)
    primary = inner[0]
    described: dict[str, Any] = {
        "error": type(error).__name__,
        "detail": message(error)[:limit],
        "cause": cause_chain(primary)[:limit],
    }
    if len(inner) > 1:
        # An anyio task group that lost several tasks at once. The count is the
        # tell that this was a group rather than a single failure, and the types
        # say whether they all died of the same thing.
        described["grouped"] = [type(each).__name__ for each in inner][:8]
    return described
