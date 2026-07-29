"""Everything a consumer can ask the agent to *do*.

The counterpart to `queries`: that module reads, this one acts. Both are
delegation — the decisions live in the domain and the services, and a method
here that grows a branch has taken a decision that belongs somewhere else.

Guidelines §5.3 require this: the CLI and the dashboard hold no business logic,
which is only enforceable if there is one place they both have to come through.
"""

from pathlib import Path
from typing import Any

from ..net.opponent_wait import wait_for_opponent
from ..net.preflight import PreflightReport, run_preflight
from ..replay.verifier import ReplayResult, verify_log
from ..reporting.archive import ArchiveReport, build_archive


class OpponentUnreachableError(RuntimeError):
    """The opponent never came up within the wait window."""


class AgentActions:
    """Operations, bound to whichever services were wired in."""

    def __init__(
        self,
        server: Any = None,
        tunnel: Any = None,
        negotiation: Any = None,
        checks: dict[str, Any] | None = None,
        workspace: Path | None = None,
        emit: Any = None,
        dashboard: Any = None,
        match: Any = None,
        opponent_url: str = "",
        wait_seconds: float = 900.0,
    ) -> None:
        """Hold the services; all are optional before a match is configured."""
        self._server = server
        self._tunnel = tunnel
        self._negotiation = negotiation
        self._checks = checks or {}
        self._workspace = workspace or Path("workspace")
        self._emit = emit or (lambda _event: None)
        self._dashboard = dashboard
        self._match = match
        self._opponent_url = opponent_url
        self._wait_seconds = wait_seconds
        self._file_match: Any = None
        #: Where the last match's artifacts were written, for the CLI and dashboard.
        self.last_artifacts: dict[str, Any] = {}

    @property
    def public_url(self) -> str:
        """The address peers should call — only if it actually answers.

        `alive()`, not "a tunnel is configured". The tunnel object is built from
        config whether or not it was started, so `--no-tunnel` used to print the
        permanent hostname anyway: a URL nothing was listening on, ready to be
        pasted to an opponent who would find us unreachable and reasonably
        conclude we had not turned up.

        The local URL is the honest answer when the tunnel is down. It is
        useless to a remote opponent, which is the point — it says *we are not
        publicly reachable* instead of claiming we are.
        """
        if self._tunnel is not None and self._tunnel.alive():
            return self._tunnel.public_url
        return self._server.url if self._server is not None else ""

    @property
    def opponent_url(self) -> str:
        """Where we would dial for the next match, empty until one is scheduled.

        Read-only and public so the liveness panel can probe it without the UI
        reaching past the facade (ADR-005). Empty is a scheduling state, not a
        fault — see `net/liveness.py`.
        """
        return self._opponent_url

    @property
    def serving(self) -> bool:
        """Whether the MCP server is accepting calls."""
        return bool(self._server is not None and self._server.running)

    def start_peer(self, with_tunnel: bool = True, with_dashboard: bool = True) -> str:
        """Bring the agent online and return the URL peers should use."""
        if self._server is None:
            raise RuntimeError("no MCP server configured — load a config first")
        self._server.start()
        if with_tunnel and self._tunnel is not None:
            self._tunnel.start()
        if with_dashboard and self._dashboard is not None:
            self.start_dashboard()
        self._emit({"event": "agent.online", "url": self.public_url})
        return self.public_url

    def attach_dashboard(self, dashboard: Any) -> None:
        """Wire in a dashboard server after construction.

        Needed because the dashboard reads the SDK, the SDK holds these
        actions, and these actions start the dashboard — one of the three has
        to be connected last.
        """
        self._dashboard = dashboard

    def start_dashboard(self) -> str:
        """Serve the UI; returns its URL, or "" when it could not start."""
        if self._dashboard is None or not self._dashboard.start():
            return ""
        return self._dashboard.url

    def stop_peer(self) -> None:
        """Shut down cleanly; safe to call when nothing is running.

        Only the tunnel needs stopping: it is a real child process that would
        otherwise outlive us and keep a public hostname pointing at a dead port.
        The MCP server runs on a daemon thread and is reaped when the process
        exits, which is what makes Ctrl-C sufficient.
        """
        if self._tunnel is not None:
            self._tunnel.stop()
        self._emit({"event": "agent.offline"})

    def attach_match(self, runner: Any) -> None:
        """Wire in the match runner once the opponent URL is known."""
        self._match = runner

    def play_match(self, wait_seconds: float | None = None) -> Any:
        """Play the agreed series against the opponent and return the result.

        Waits for the opponent to be listening first. Both peers dial each
        other, so without this the result depends on who started first: the
        earlier peer spends its retries on a dead port and exits, and the later
        one then finds nobody. Two teams agreeing "20:00" will not both be
        listening at 20:00:00, and a cold start is ~15 s.
        """
        if self._match is None:
            raise RuntimeError("no match configured — set network.opponent_url first")
        # The result was previously discarded, so a wait that expired went on to
        # play anyway: `opponent.absent waited=120` was recorded and the
        # handshake then died three stack frames deep in a 502. The wait already
        # knew. Saying so is the whole point of having run it.
        wait_seconds = self._wait_seconds if wait_seconds is None else wait_seconds
        waiting = self._opponent_url and wait_seconds > 0
        if waiting and not wait_for_opponent(
            self._opponent_url, timeout=wait_seconds, emit=self._emit
        ):
                raise OpponentUnreachableError(
                    f"opponent did not answer at {self._opponent_url} after "
                    f"{wait_seconds:.0f}s — check they have started, and that "
                    "their URL is current (a quick tunnel changes on restart)"
                )
        self._emit({"event": "match.starting"})
        result = self._match.play_series()
        self._emit({"event": "match.finished", "games": len(self._match.games)})
        self._file(result)
        return result

    def attach_filer(self, filer: Any) -> None:
        """Wire in the thing that turns a finished match into its artifacts."""
        self._file_match = filer

    def _file(self, result: Any) -> None:
        """Write the artifacts and send the report; never lose the series to it.

        A match that is played but not filed scores nothing (rule 35), so the
        failure is loud. It is caught rather than raised because the series is
        already over and its outcome is worth keeping even if the paperwork
        fails — the operator gets an event naming what went wrong.
        """
        if self._file_match is None:
            self._emit({"event": "artifacts.skipped", "reason": "no filer configured"})
            return
        try:
            self._file_match(self._match.games, self._match.tracker.outcomes, result)
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            self._emit({"event": "artifacts.failed", "error": f"{type(error).__name__}: {error}"})

    @property
    def games(self) -> list[dict[str, Any]]:
        """Every mini-game played so far, for the report and the dashboard."""
        return list(getattr(self._match, "games", []))

    def preflight(self) -> PreflightReport:
        """Run the match-day checks and report what is not ready."""
        return run_preflight(self._checks)

    def propose_terms(self, terms: dict[str, Any] | None = None) -> dict[str, Any]:
        """Open a negotiation with our terms (or a supplied set)."""
        return self._negotiation.propose(terms)

    def approve_terms(
        self, terms: dict[str, Any], identity: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Agree terms a human has reviewed — the approval step (FR-NEG-4)."""
        return self._negotiation.agree(terms, identity)

    def verify_log(self, log: Path) -> ReplayResult:
        """Re-hash a match log, ours or an opponent's (book rule 20)."""
        return verify_log(log)

    def archive_match(self, destination: Path, extra: dict[str, Path] | None = None) -> ArchiveReport:
        """Bundle the match evidence into one file, secrets excluded."""
        sources: dict[str, Path] = {
            "artifacts": self._workspace / "artifacts",
            "events": self._workspace / "events.jsonl",
            "config": self._workspace / "config",
            **(extra or {}),
        }
        report = build_archive(destination, sources)
        self._emit({"event": "match.archived", "path": str(destination), "files": report.file_count})
        return report
