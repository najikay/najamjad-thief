"""The command line: argument parsing, one SDK call, an exit code.

Guidelines §5.3 put every business decision behind the SDK, so each verb here is
deliberately thin — a meta-test enforces it. If a command starts needing a
branch to decide *what* to do, that decision belongs in `sdk.actions`.

Exit codes are the contract, because these run in scripts:
    0  the thing worked
    1  it ran and the answer was bad (preflight not ready, log tampered)
    2  it could not run (missing or unreadable input)

Options are declared with `Annotated` rather than call-valued defaults: the
older typer idiom evaluates at import time, which both trips ruff's B008 and
would read the filesystem for a default nobody asked for.
"""

import contextlib
import signal
import threading
from pathlib import Path
from typing import Annotated

import typer

from .sdk.bootstrap import build_sdk
from .shared.version import CODE_VERSION


def _practice(enabled: bool) -> None:
    """Arm practice mode for this process only.

    Set before the SDK is built, because everything downstream reads the mode
    fresh at the moment it needs it.
    """
    if enabled:
        import os

        from .shared.practice import PRACTICE_ENV

        os.environ[PRACTICE_ENV] = "1"


def _sdk(**kwargs):
    """Build the SDK, turning a bad `--opponent` into a message not a traceback.

    A mistyped card name is operator error minutes before a match. The
    exception already names the available cards; a stack trace above it only
    buries that.
    """
    from .shared.opponents import OpponentError

    try:
        return build_sdk(**kwargs)
    except OpponentError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=UNUSABLE_INPUT) from error


app = typer.Typer(add_completion=False, help="NajAmjad P2P cops-and-thieves agent.")

UNUSABLE_INPUT = 2
SHUTDOWN_POLL_SECONDS = 0.5

ConfigOption = Annotated[Path | None, typer.Option("--config", help="role config directory")]
RoleOption = Annotated[str, typer.Option("--role", help="police or thief; default: this repo's")]
#: Name of a card in `opponents/`. Carries their URL and group_id, so a match
#: needs no hand-edit of the tracked config (see shared/opponents.py).
OpponentOption = Annotated[str, typer.Option("--opponent", help="name of a card in opponents/")]
#: A practice-only identity override. Never for a counted match: the committed
#: config carries our real group_id and a test pins it.
GroupIdOption = Annotated[str, typer.Option("--group-id", help="override our group_id (practice only)")]
#: Play deterministically: no scent, no hints, and no LLM call at all. For
#: mirroring a peer who transmits nothing — several do — and for a run whose
#: cost and timing are entirely predictable.
QuietOption = Annotated[bool, typer.Option("--quiet/--talk", help="emit no scent or hints; no LLM")]
#: Runs this process in practice mode without touching any tracked file.
PracticeOption = Annotated[bool, typer.Option("--practice/--counted", help="redirect reports to the operator")]


@app.command()
def peer(
    config: ConfigOption = None,
    role: str = "",
    tunnel: Annotated[bool, typer.Option("--tunnel/--no-tunnel")] = True,
    dashboard: Annotated[bool, typer.Option("--dashboard/--no-dashboard")] = True,
    opponent: OpponentOption = "",
    group_id: GroupIdOption = "",
    practice: PracticeOption = False,
) -> None:
    """Bring the agent online and serve until interrupted."""
    _practice(practice)
    sdk = _sdk(config=config, role=role, dashboard=dashboard, opponent=opponent or None, group_id=group_id or None)
    url = sdk.actions.start_peer(with_tunnel=tunnel, with_dashboard=dashboard)
    typer.echo(f"agent online at {url}")
    _serve_until_interrupted(sdk)


@app.command()
def match(
    config: ConfigOption = None,
    role: RoleOption = "",
    tunnel: Annotated[bool, typer.Option("--tunnel/--no-tunnel")] = False,
    dashboard: Annotated[bool, typer.Option("--dashboard/--no-dashboard")] = False,
    opponent: OpponentOption = "",
    group_id: GroupIdOption = "",
    practice: PracticeOption = False,
    quiet: QuietOption = False,
) -> None:
    """Serve, then play the agreed series against the configured opponent."""
    _practice(practice)
    sdk = _sdk(config=config, role=role, dashboard=dashboard, opponent=opponent or None,
               group_id=group_id or None, quiet=quiet)
    typer.echo(f"agent online at {sdk.actions.start_peer(with_tunnel=tunnel, with_dashboard=dashboard)}")
    from .sdk.actions import OpponentUnreachableError

    try:
        result = sdk.actions.play_match()
    except OpponentUnreachableError as absent:
        typer.echo(str(absent), err=True)
        raise typer.Exit(code=UNUSABLE_INPUT) from absent
    for game in sdk.actions.games:
        typer.echo(f"  g{game['sub_game']:02d} {game['role']:6} {game['end_reason']:14} {game['audit']}")
    typer.echo(f"series: {result.total_score} winner={result.winner_group or 'tie'}")
    if dashboard:
        # The process used to exit here, taking the dashboard with it — so the
        # socket dropped ("reconnecting in 10s…") and the report panel froze on
        # "waiting for the match to end" moments after the mail had gone. The
        # one moment an operator most wants to read those panels is now.
        typer.echo("dashboard still serving — Ctrl+C when you have finished reading it")
        _serve_until_interrupted(sdk)


@app.command()
def preflight(
    config: ConfigOption = None,
    role: RoleOption = "",
    opponent: OpponentOption = "",
    group_id: GroupIdOption = "",
    practice: PracticeOption = False,
) -> None:
    """Run the match-day checks and print the checklist."""
    _practice(practice)
    report = _sdk(config=config, role=role, dashboard=False,
                  opponent=opponent or None, group_id=group_id or None).actions.preflight()
    typer.echo(report.render())
    raise typer.Exit(code=report.exit_code)


@app.command()
def replay(
    log: Annotated[Path, typer.Argument(help="path to a log_*.json artifact")],
    serve: Annotated[bool, typer.Option("--serve", help="open the viewer")] = False,
    port: Annotated[int, typer.Option("--port", help="viewer port")] = 8100,
) -> None:
    """Verify a match log, or open the replay viewer on it."""
    if not log.exists():
        typer.echo(f"no such log: {log}", err=True)
        raise typer.Exit(code=UNUSABLE_INPUT)
    from .replay.__main__ import main as replay_main

    argv = ["--log", str(log), "--port", str(port)] + ([] if serve else ["--check"])
    raise typer.Exit(code=replay_main(argv))


@app.command()
def archive(
    destination: Annotated[Path, typer.Argument(help="path to the .zip to write")],
    config: ConfigOption = None,
    role: RoleOption = "",
) -> None:
    """Bundle the match evidence into one archive (secrets excluded)."""
    sdk = build_sdk(config=config, role=role, dashboard=False)
    report = sdk.actions.archive_match(destination)
    typer.echo(f"archived {report.file_count} file(s) to {destination}")
    for entry in report.excluded_secrets:
        typer.echo(f"  withheld secret: {entry}", err=True)
    # An empty archive with no explanation reads as a bug. Name what was absent.
    for source in report.missing_sources:
        typer.echo(f"  nothing found for: {source}", err=True)


@app.command()
def version() -> None:
    """Print the agent version."""
    typer.echo(CODE_VERSION)


def _serve_until_interrupted(sdk: object) -> None:
    """Block until Ctrl-C, then stop the tunnel before exiting.

    An unstopped tunnel keeps a public hostname pointing at a dead port, which
    is how an opponent ends up reporting us unreachable after we thought we had
    shut down cleanly.

    An earlier version used `signal.sigwait`, which needs the signals blocked
    first — unblocked, it never received them, and Ctrl-C left the agent
    running until something killed it. A handler plus a polled wait is portable
    (Windows has no `pthread_sigmask`) and interrupts reliably, because the
    timeout guarantees the interpreter returns to run the handler.
    """
    stop = threading.Event()
    received: list[int] = []

    def _handle(signum: int, _frame: object) -> None:
        received.append(signum)
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is not None:
            with contextlib.suppress(OSError, ValueError):
                signal.signal(sig, _handle)
    while not stop.wait(SHUTDOWN_POLL_SECONDS):
        pass
    label = signal.Signals(received[0]).name if received else "shutdown"
    typer.echo(f"\nreceived {label}, shutting down")
    sdk.actions.stop_peer()  # type: ignore[attr-defined]


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
