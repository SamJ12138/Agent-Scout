"""Command line.

Exit codes: 0 success, 1 error (one line on stderr), 2 usage error (argparse).
A site that is blocked or unreachable is a result, not an error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, obs


class CliError(Exception):
    """An error reported to the user as one line, exit code 1."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-scout",
        description="Profile AI marketing-agent products from their own public websites. "
                    "Every value carries the page and sentence it came from; "
                    "anything a site does not state is reported as unknown.",
    )
    parser.add_argument("--version", action="version", version=f"agent-scout {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    report_log = commands.add_parser(
        "report-log", help="summarise a run log: error counts and stage durations")
    report_log.add_argument("file", type=Path, help="a logs/run_<id>.jsonl file")
    return parser


def _cmd_report_log(args: argparse.Namespace) -> int:
    try:
        text = obs.report_log(args.file)
    except OSError as exc:
        obs.emit("report", "fail", error_type="log_unreadable", path=str(args.file))
        raise CliError(f"cannot read {args.file}: {exc.strerror or exc}") from None
    except obs.LogFormatError as exc:
        obs.emit("report", "fail", error_type="log_format", path=str(args.file))
        raise CliError(str(exc)) from None
    sys.stdout.write(text)
    return 0


COMMANDS = {"report-log": _cmd_report_log}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except CliError as exc:
        obs.emit("run", "fail", error_type="cli_error", message=str(exc))
        print(f"agent-scout: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
