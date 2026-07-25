"""The loaded log a viewer is currently looking at.

Kept apart from the routes so the CLI, the tests and the web page all drive the
same object. A failed load leaves the previous log in place and records why:
opening a bad file should not blank the screen you were reading.
"""

from pathlib import Path
from typing import Any

from .loader import ReplayLoadError
from .rebuild import summary_view, timeline
from .verifier import ReplayResult, verify_log


class ReplaySession:
    """One loaded log, with its verdict and per-step views."""

    def __init__(self, source: Any = None) -> None:
        """Optionally load a log immediately."""
        self._result: ReplayResult | None = None
        self._source = ""
        self.error = ""
        if source is not None:
            self.load(source)

    @property
    def loaded(self) -> bool:
        """Whether a log is currently open."""
        return self._result is not None

    @property
    def result(self) -> ReplayResult | None:
        """The verification result, if a log is open."""
        return self._result

    def load(self, source: Any) -> bool:
        """Open a log; returns False and records `error` if it cannot be read."""
        try:
            self._result = verify_log(source)
        except ReplayLoadError as failure:
            self.error = str(failure)
            return False
        self._source = str(source) if isinstance(source, str | Path) else "<in-memory>"
        self.error = ""
        return True

    def summary(self) -> dict[str, Any]:
        """Header state: banner, counts, and the log's own metadata."""
        if self._result is None:
            return {"loaded": False, "error": self.error}
        return {"loaded": True, "source": self._source, **summary_view(self._result)}

    def steps(self) -> list[dict[str, Any]]:
        """Every step's view, in record order."""
        return timeline(self._result) if self._result is not None else []

    def step(self, index: int) -> dict[str, Any]:
        """One step by position, for forward/back navigation."""
        views = self.steps()
        if not views:
            return {"available": False, "error": self.error or "no log loaded"}
        if not 0 <= index < len(views):
            return {"available": False, "error": f"step {index} is outside 0..{len(views) - 1}"}
        return {"available": True, "total": len(views), **views[index]}
