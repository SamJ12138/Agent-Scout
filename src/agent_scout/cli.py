"""Command line.

Exit codes: 0 success, 1 error (one line on stderr), 2 usage error (argparse).
A site that is blocked or unreachable is a result, not an error.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
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
    run.add_argument("--llm", action="store_true",
                     help="also ask a language model for each field; values whose quote is not on the "
                          "fetched pages are dropped (off by default; sends page text to the provider)")
    run.add_argument("--llm-provider", choices=["openai-compatible", "anthropic"], help="LLM API style")
    run.add_argument("--llm-base-url", help="base URL of an openai-compatible API, e.g. https://api.deepseek.com")
    run.add_argument("--llm-model", help="model name")

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
    run_id = obs.new_run_id()
    try:
        log = obs.EventLog(args.log_dir / f"run_{run_id}.jsonl", run_id)
    except OSError as exc:
        obs.emit("run", "fail", error_type="log_unwritable", path=str(args.log_dir))
        raise CliError(f"cannot write the run log in {args.log_dir}: {exc.strerror or exc}") from None
    obs.set_current(log)
    write = None if args.quiet else print
    try:
        return _run(args, log, run_id, write)
    except CliError:
        obs.emit("run", "fail", error_type="cli_error")
        raise
    except Exception as exc:
        # Not expected: record the traceback in the run log, report one line.
        obs.emit("run", "fail", error_type=type(exc).__name__, traceback=traceback.format_exc())
        if os.environ.get("AGENT_SCOUT_TRACEBACK"):
            traceback.print_exc()
        raise CliError(f"unexpected {type(exc).__name__}: {' '.join(str(exc).split())[:200]} "
                       f"(traceback in {log.path}; set AGENT_SCOUT_TRACEBACK=1 to print it)") from None
    finally:
        obs.set_current(None)
        log.close()


def _run(args: argparse.Namespace, log: obs.EventLog, run_id: str, write) -> int:
    from .pipeline import run_sites
    from .reports import write_all

    with obs.span("input", path=str(args.sites)) as span:
        try:
            config = load_config(args.config, {
                "page_budget": args.page_budget, "delay_seconds": args.delay, "timeout_seconds": args.timeout,
                "llm_enabled": bool(args.llm), "llm_provider": args.llm_provider,
                "llm_base_url": args.llm_base_url, "llm_model": args.llm_model})
            sites = load_sites(args.sites)
        except (ConfigError, InputError) as exc:
            span.fail(type(exc).__name__)
            raise CliError(str(exc)) from None
        span.context["sites"] = len(sites)
    after_site = None
    llm_failures: list[str] = []
    if config.llm.enabled:
        from . import llm
        try:
            settings = llm.resolve_settings(config.llm)
        except llm.LLMError as exc:
            obs.emit("llm", "fail", error_type=exc.error_type)
            raise CliError(str(exc)) from None
        log.register_secret(settings.api_key)
        config.llm.provider, config.llm.model = settings.provider, settings.model
        client = llm.LLMClient(settings)

        def after_site(result: dict) -> None:
            pages = result.get("_pages") or []
            if llm_failures and llm_failures[-1] == "auth":
                obs.emit("llm", "skip", site=result["slug"], error_type="auth_failed_earlier")
                result["llm"] = {"status": "skipped", "added": 0, "dropped": 0, "error_type": "auth_failed_earlier"}
                return
            summary = llm.llm_pass(result, pages, client)
            if summary["status"] == "failed":
                llm_failures.append(summary["error_type"])
            if write:
                write({"ok": f"      llm: {summary['added']} added, {summary['dropped']} dropped (quote not verified)",
                       "failed": f"      llm: failed ({summary['error_type']}); rule-based values kept",
                       "skipped": "      llm: nothing sent"}[summary["status"]])

    results = run_sites(sites, config, run_id, write=write, after_site=after_site)
    try:
        paths = write_all(results, args.out)
    except OSError as exc:
        obs.emit("report", "fail", error_type="output_unwritable", path=str(args.out))
        raise CliError(f"cannot write reports in {args.out}: {exc.strerror or exc}") from None
    if write:
        write("")
        write("Reports: " + ", ".join(str(path) for path in paths))
        write(f"Log:     {log.path}")
    if llm_failures:
        raise CliError(f"the LLM pass failed ({', '.join(sorted(set(llm_failures)))}) for "
                       f"{len(llm_failures)} site{'s' if len(llm_failures) != 1 else ''}; "
                       f"the reports in {args.out} hold rule-based values for them")
    return 0


COMMANDS = {"run": _cmd_run, "report-log": _cmd_report_log}


def _tolerant_streams() -> None:
    """A console that cannot encode a character (a legacy Windows code page,
    a site name in another script) must not crash the run: show an escape."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (ValueError, OSError) as exc:
            obs.emit("run", "skip", error_type="stream_not_reconfigurable", detail=type(exc).__name__)


def main(argv: list[str] | None = None) -> int:
    _tolerant_streams()
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except CliError as exc:
        obs.emit("run", "fail", error_type="cli_error", message=str(exc))
        print(f"agent-scout: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
