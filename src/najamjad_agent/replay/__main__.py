"""Open the replay viewer on a log file.

    uv run python -m najamjad_agent.replay --log path/to/log_*.json

E20's `replay` CLI verb delegates here rather than reimplementing it. Serving
is bound to localhost on purpose: a log holds revealed nonces and positions, and
nothing about auditing it needs to be reachable from the network.
"""

import argparse
import sys
from pathlib import Path

from .verifier import verify_log


def build_parser() -> argparse.ArgumentParser:
    """Command-line surface of the viewer."""
    parser = argparse.ArgumentParser(prog="najamjad-replay", description=__doc__)
    parser.add_argument("--log", type=Path, required=True, help="path to a log_*.json artifact")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (localhost by default)")
    parser.add_argument("--port", type=int, default=8100, help="port to serve the viewer on")
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the verdict and exit non-zero if tampered, without serving",
    )
    return parser


def check(log: Path) -> int:
    """Verify a log and report the verdict; the exit code is the answer."""
    result = verify_log(log)
    print(f"{result.banner}: {len(result.steps)} steps, {len(result.failed_indices)} failed")
    for step in result.steps:
        if not step.verified:
            print(f"  step {step.step} (record {step.index}): {step.reason}")
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    """Verify the log, then serve the viewer unless `--check` was given."""
    args = build_parser().parse_args(argv)
    if not args.log.exists():
        print(f"no such log: {args.log}", file=sys.stderr)
        return 2
    if args.check:
        return check(args.log)

    import uvicorn

    from .app import create_replay_app

    print(f"replay viewer on http://{args.host}:{args.port}/replay")
    uvicorn.run(create_replay_app(args.log), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
