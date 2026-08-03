"""Writing what we can, when one artifact cannot be written.

The filer used to write straight through: declaration, then a config and a log
per mini-game, then the result. Any one of those raising aborted the rest —
and `write_result` is *last*, so the single artifact that gets emailed and
graded was the most likely to be lost.

That is not theoretical. Against uoh-sqak three mini-games were abandoned
mid-play, their logs held no sealed records, the schema refused an empty
`records` list, and the whole run died on the first one:

    egress.blocked kind=log problems=["records: List should have at least 1
        item after validation, not 0"]
    artifacts.failed error=EgressBlockedError

Zero artifacts for a six-game series. Book rule 35 scores a missing report as
not having played, so a defect in one mini-game's log converted a 15-60 loss
into a nothing — strictly the worse outcome.

The empty-records case is fixed at the schema, but the fragility underneath it
is the real defect: **no single artifact may be able to suppress the others.**
A failure here is recorded loudly and skipped, because a partial report that
names its own gap is worth more than no report at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..shared.events import Emit


def attempt(
    label: str,
    write: Callable[[], Any],
    emit: Emit | None = None,
) -> str | None:
    """Write one artifact; on failure record it and return None.

    Input: a label for the event log, and a thunk that writes and returns a path.
    Output: the path as a string, or None when the write failed.
    Setup: none.

    Never raises. The caller keeps going and the operator learns which artifact
    is missing and why — the alternative, discovered the hard way, is silence
    plus an empty directory.
    """
    publish = emit or (lambda _event: None)
    try:
        return str(write())
    except Exception as error:  # noqa: BLE001 - one artifact must not sink the rest
        publish({
            "event": "artifact.skipped",
            "artifact": label,
            "error": f"{type(error).__name__}: {error}",
        })
        return None


def missing(written: dict[str, Any]) -> list[str]:
    """Which artifacts we failed to produce, for the closing event.

    `result` absent is the serious one: that is the graded file. Naming it
    explicitly means a match cannot end with the operator believing a report
    went out when it did not.
    """
    gaps = [name for name, value in written.items() if value is None]
    gaps += [
        name for name, value in written.items()
        if isinstance(value, list) and any(entry is None for entry in value)
    ]
    return sorted(set(gaps))
