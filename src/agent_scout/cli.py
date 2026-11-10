"""Command line.

Exit codes: 0 success, 1 error (one line on stderr), 2 usage error (argparse).
A site that is blocked or unreachable is a result, not an error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, obs
from .config import ConfigError, load_config
from .inputs import InputError, load_sites


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

    run = commands.add_parser(
        "run", help="profile the sites listed in a file and write the reports",
        description="Fetch each site politely (robots.txt, Crawl-delay, a delay between requests), "
                    "extract the profile fields with their evidence and write results.json, "
                    "results.csv, report.md and report.html. A site that is blocked or unreachable "
                    "is reported as such; it is not an error.")
    run.add_argument("sites", type=Path, help="sites.yaml (list of {name, url}) or a text file of URLs")
    run.add_argument("-o", "--out", type=Path, default=Path("out"), help="output directory (default: out)")
    run.add_argument("--config", type=Path, help="YAML settings file (see config.example.yaml)")
    run.add_argument("--page-budget", type=int, help="pages per site, homepage included (default 6)")
    run.add_argument("--delay", type=float, help="seconds between requests to one host (default 1.5)")
    run.add_argument("--timeout", type=float, help="seconds per request (default 20)")
    run.add_argument("--log-dir", type=Path, default=Path("logs"), help="directory for run_<id>.jsonl (default: logs)")
    run.add_argument("--quiet", action="store_true", help="print nothing but errors")

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


def _cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import run_sites
    from .reports import write_all

    run_id = obs.new_run_id()
    try:
        log = obs.EventLog(args.log_dir / f"run_{run_id}.jsonl", run_id)
    except OSError as exc:
        obs.emit("run", "fail", error_type="log_unwritable", path=str(args.log_dir))
        raise CliError(f"cannot write the run log in {args.log_dir}: {exc.strerror or exc}") from None
    obs.set_current(log)
    write = None if args.quiet else print
    try:
        with obs.span("input", path=str(args.sites)) as span:
            try:
                config = load_config(args.config, {"page_budget": args.page_budget, "delay_seconds": args.delay,
                                                   "timeout_seconds": args.timeout})
                sites = load_sites(args.sites)
            except (ConfigError, InputError) as exc:
                span.fail(type(exc).__name__)
                raise CliError(str(exc)) from None
            span.context["sites"] = len(sites)
        results = run_sites(sites, config, run_id, write=write)
        try:
            paths = write_all(results, args.out)
        except OSError as exc:
            obs.emit("report", "fail", error_type="output_unwritable", path=str(args.out))
            raise CliError(f"cannot write reports in {args.out}: {exc.strerror or exc}") from None
        if write:
            write("")
            write("Reports: " + ", ".join(str(path) for path in paths))
            write(f"Log:     {log.path}")
        return 0
    finally:
        obs.set_current(None)
        log.close()


COMMANDS = {"run": _cmd_run, "report-log": _cmd_report_log}


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
