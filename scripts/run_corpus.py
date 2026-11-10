"""Run Agent Scout on the real-site corpus and score it against the ground truth.

    python scripts/run_corpus.py

Reads   docs/real-corpus/sites.yaml and docs/real-corpus/ground-truth/<slug>.json
Writes  docs/real-corpus/results/latest.json   the tool's results.json
        docs/real-corpus/scores.md             site status and match / partial /
                                               mismatch / missing per site and field
        docs/real-corpus/report.html           the HTML report of that run

The tool runs with its default settings (rule-based extraction, no LLM pass).
This needs to reach the public web, so it is run by the GitHub Actions
workflow .github/workflows/corpus.yml, not by the test suite.

Exit code: 0 when the tool ran, whatever the sites answered: a blocked or
unreachable site is a result and is recorded as such. Non-zero only when the
tool itself failed (bad input, crash).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_scout import scoring  # noqa: E402
from agent_scout.cli import main as agent_scout_main  # noqa: E402
from agent_scout.model import FIELDS  # noqa: E402
from agent_scout.reports import REACHABLE, STATUS_LABELS  # noqa: E402

CORPUS = ROOT / "docs" / "real-corpus"


def scores_markdown(results: dict, score: scoring.RunScore) -> str:
    sites = results["sites"]
    read = sum(1 for site in sites if site["status"] in REACHABLE)
    totals = score.totals()
    lines = [
        "# Real-site corpus: scores",
        "",
        "Written by `scripts/run_corpus.py` (GitHub Actions workflow `corpus`). Do not edit by hand.",
        "",
        f"- Run `{results['run_id']}`, finished {results['finished_at']}, agent-scout {results['tool']['version']}",
        f"- Settings: rule-based extraction only (no LLM pass), {results['settings']['page_budget']} pages per site, "
        f"{results['settings']['delay_seconds']:g} s between requests to one host, robots.txt honoured",
        f"- Sites read: {read} of {len(sites)} (read or partly read); the others are listed below with the reason",
        f"- Site-fields: {totals['match']} match, {totals['partial']} partial, {totals['mismatch']} mismatch, "
        f"{totals['missing']} missing, of {sum(totals.values())}",
        "",
        "How to read this: the reference profiles in `ground-truth/` were written from tool-mediated "
        "reads of each product's own site and committed before the tool was run on these sites (see "
        "`ground-truth/README.md` for the method and its limits). `match`, `partial`, `mismatch` and `missing` are defined in `src/agent_scout/scoring.py`. "
        "A site the tool could not read has every field unknown, so each field the reference knows counts "
        "as `missing` there: those rows measure reachability, not extraction. The corpus has no product "
        "whose site says it only drafts, so nothing here tests `can_execute: false`. Category and task "
        "lists involve judgment; one extra or one absent list value makes a field `partial`.",
        "",
        "## Site status",
        "",
        "| site | status | detail | pages read |",
        "|---|---|---|---|",
    ]
    for site in sites:
        pages = sum(1 for page in site["pages"] if page["outcome"] == "fetched")
        detail = " ".join(str(site["status_detail"]).split()).replace("|", "\\|")
        lines.append(f"| {site['slug']} | {STATUS_LABELS[site['status']]} | {detail} | {pages} |")
    lines += ["", "## Per site and field", "", score.markdown().rstrip(), "",
              "## Fields on sites that were read", "",
              "The same counts restricted to sites with status read or partly read.", "",
              "| field | match | partial | mismatch | missing |", "|---|---|---|---|---|"]
    readable = {site["slug"] for site in sites if site["status"] in REACHABLE}
    for name in FIELDS:
        counts = {outcome: 0 for outcome in scoring.OUTCOMES}
        for slug, site_score in score.sites.items():
            if site_score.status in REACHABLE and name in site_score.outcomes:
                counts[site_score.outcomes[name].outcome] += 1
        lines.append(f"| {name} | " + " | ".join(str(counts[outcome]) for outcome in scoring.OUTCOMES) + " |")
    lines += ["", f"Sites in this second table: {len(readable)}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sites", type=Path, default=CORPUS / "sites.yaml")
    parser.add_argument("--ground-truth", type=Path, default=CORPUS / "ground-truth")
    parser.add_argument("--out", type=Path, default=CORPUS, help="where results/latest.json, scores.md and report.html go")
    parser.add_argument("--keep-run-dir", type=Path, help="keep the full run output (reports and log) in this directory")
    parser.add_argument("--delay", type=float, help="override the delay between requests (tests only)")
    args = parser.parse_args(argv)

    run_dir = args.keep_run_dir or Path(tempfile.mkdtemp(prefix="agent-scout-corpus-"))
    command = ["run", str(args.sites), "-o", str(run_dir / "out"), "--log-dir", str(run_dir / "logs")]
    if args.delay is not None:
        command += ["--delay", str(args.delay)]
    code = agent_scout_main(command)
    if code != 0:
        print(f"run_corpus: the tool exited with code {code}; nothing was written", file=sys.stderr)
        return code

    results = json.loads((run_dir / "out" / "results.json").read_text(encoding="utf-8"))
    score = scoring.score_results(results, args.ground_truth)
    (args.out / "results").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_dir / "out" / "results.json", args.out / "results" / "latest.json")
    shutil.copyfile(run_dir / "out" / "report.html", args.out / "report.html")
    (args.out / "scores.md").write_text(scores_markdown(results, score), encoding="utf-8", newline="\n")
    print()
    print(score.table())
    print(f"Wrote {args.out / 'results' / 'latest.json'}, {args.out / 'scores.md'}, {args.out / 'report.html'}")
    if not args.keep_run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
