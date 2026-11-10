"""Run Agent Scout on the real-site corpus and score it against the ground truth.

    python scripts/run_corpus.py

Reads   docs/real-corpus/sites.yaml and docs/real-corpus/ground-truth/<slug>.json
Writes  docs/real-corpus/results/latest.json   the tool's results.json
        docs/real-corpus/scores.md             site status and match / partial /
                                               mismatch / missing per site and field
        docs/real-corpus/report.html           the HTML report of that run
        README.md                              the block between the real-site-results
                                               markers, so its numbers are never typed by hand

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
import re
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


README_START = "<!-- real-site-results:start (written by scripts/run_corpus.py from docs/real-corpus/scores.md) -->"
README_END = "<!-- real-site-results:end -->"


def parse_scores(text: str) -> dict:
    """The figures of a scores.md: run, sites read, totals and the per-field table."""
    run = re.search(r"^- Run `([^`]+)`, finished (\S+),", text, re.MULTILINE)
    read = re.search(r"^- Sites read: (\d+) of (\d+)", text, re.MULTILINE)
    totals = re.search(r"^- Site-fields: (\d+) match, (\d+) partial, (\d+) mismatch, (\d+) missing, of (\d+)",
                       text, re.MULTILINE)
    if not (run and read and totals):
        raise ValueError("not a scores.md written by run_corpus.py")
    fields: dict[str, dict[str, int]] = {}
    table = text[text.index("| field | match | partial | mismatch | missing |"):]
    for line in table.splitlines()[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] not in FIELDS:
            break
        fields[cells[0]] = dict(zip(scoring.OUTCOMES, (int(cell) for cell in cells[1:])))
    return {"run_id": run.group(1), "finished": run.group(2),
            "sites_read": int(read.group(1)), "sites": int(read.group(2)),
            "totals": dict(zip(scoring.OUTCOMES, (int(g) for g in totals.groups()[:4]))),
            "site_fields": int(totals.group(5)), "fields": fields}


def totals_sentence(scores: dict) -> str:
    totals = scores["totals"]
    return (f"{totals['match']} match, {totals['partial']} partial, {totals['mismatch']} mismatch, "
            f"{totals['missing']} missing of {scores['site_fields']} site-fields")


def first_run_id() -> str | None:
    """The id of the first real-site run, kept in docs/real-corpus/run-1/scores.md."""
    path = CORPUS / "run-1" / "scores.md"
    return parse_scores(path.read_text(encoding="utf-8"))["run_id"] if path.is_file() else None


def readme_block(scores: dict, first: str | None = None) -> str:
    """The README's real-site results, from the figures of a scores.md.
    ``first`` is the id of the first run: the block says whether this is it."""
    if first is None or scores["run_id"] == first:
        standing = ("This is the first run on real sites. Rules adjusted after it have not been run on the "
                    "corpus yet.")
    else:
        standing = ("Rules were adjusted after the first run on these sites, so this is not a held-out score "
                    "(see below).")
    lines = [README_START,
             f"Latest run on the real-site corpus: `{scores['run_id']}`, finished {scores['finished']}. "
             f"Sites read: {scores['sites_read']} of {scores['sites']}. {standing}",
             "",
             f"**{totals_sentence(scores)}.**",
             "",
             "| field | match | partial | mismatch | missing |",
             "|---|---|---|---|---|"]
    for name in FIELDS:
        row = scores["fields"][name]
        lines.append(f"| {name} | " + " | ".join(str(row[outcome]) for outcome in scoring.OUTCOMES) + " |")
    lines.append(README_END)
    return "\n".join(lines)


def update_readme(readme: Path, scores_text: str) -> bool:
    """Replace the marked block of ``readme``; False when it has no such block."""
    text = readme.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    start, end = text.index(README_START), text.index(README_END) + len(README_END)
    readme.write_text(text[:start] + readme_block(parse_scores(scores_text), first_run_id()) + text[end:],
                      encoding="utf-8", newline="\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sites", type=Path, default=CORPUS / "sites.yaml")
    parser.add_argument("--ground-truth", type=Path, default=CORPUS / "ground-truth")
    parser.add_argument("--out", type=Path, default=CORPUS, help="where results/latest.json, scores.md and report.html go")
    parser.add_argument("--keep-run-dir", type=Path, help="keep the full run output (reports and log) in this directory")
    parser.add_argument("--delay", type=float, help="override the delay between requests (tests only)")
    parser.add_argument("--readme", type=Path,
                        help="README whose real-site-results block is rewritten "
                             "(default: the project README, when --out is the project's corpus directory)")
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
    scores_text = scores_markdown(results, score)
    (args.out / "scores.md").write_text(scores_text, encoding="utf-8", newline="\n")
    print()
    print(score.table())
    print(f"Wrote {args.out / 'results' / 'latest.json'}, {args.out / 'scores.md'}, {args.out / 'report.html'}")
    readme = args.readme or (ROOT / "README.md" if args.out.resolve() == CORPUS.resolve() else None)
    if readme is not None and update_readme(readme, scores_text):
        print(f"Updated the real-site results block of {readme}")
    if not args.keep_run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
