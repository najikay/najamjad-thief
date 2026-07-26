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

import signal
from pathlib import Path
from typing import Annotated

import typer

from .sdk.bootstrap import build_sdk
from .shared.version import CODE_VERSION

app = typer.Typer(add_completion=False, help="NajAmjad P2P cops-and-thieves agent.")

UNUSABLE_INPUT = 2

ConfigOption = Annotated[Path | None, typer.Option("--config", help="role config directory")]
RoleOption = Annotated[str, typer.Option("--role", help="police or thief; default: this repo's")]


@app.command()
def peer(
    config: ConfigOption = None,
    role: str = "",
    tunnel: Annotated[bool, typer.Option("--tunnel/--no-tunnel")] = True,
    dashboard: Annotated[bool, typer.Option("--dashboard/--no-dashboard")] = True,
) -> None:
    """Bring the agent online and serve until interrupted."""
    sdk = build_sdk(config=config, role=role, dashboard=dashboard)
    url = sdk.actions.start_peer(with_tunnel=tunnel, with_dashboard=dashboard)
    typer.echo(f"agent online at {url}")
    _serve_until_interrupted(sdk)


@app.command()
def preflight(config: ConfigOption = None, role: RoleOption = "") -> None:
    """Run the match-day checks and print the checklist."""
    report = build_sdk(config=config, role=role, dashboard=False).actions.preflight()
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
    """
    stop = signal.sigwait([signal.SIGINT, signal.SIGTERM])
    typer.echo(f"\nreceived {signal.Signals(stop).name}, shutting down")
    sdk.actions.stop_peer()  # type: ignore[attr-defined]


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
