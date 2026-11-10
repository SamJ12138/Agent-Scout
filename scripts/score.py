"""Score a results.json against a directory of ground-truth files.

    python scripts/score.py out/results.json tests/fixtures/ground-truth

Prints one row per site and one column per field with match / partial /
mismatch / missing (definitions: src/agent_scout/scoring.py). Exit code 0;
with --require-all-match, 1 unless every field of every site matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_scout import scoring  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results", type=Path, help="results.json written by agent-scout run")
    parser.add_argument("ground_truth", type=Path, help="directory of <slug>.json ground-truth files")
    parser.add_argument("--markdown", action="store_true", help="print Markdown tables instead of plain text")
    parser.add_argument("--require-all-match", action="store_true", help="exit 1 unless everything matches")
    args = parser.parse_args(argv)
    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"score: error: cannot read {args.results}: {exc}", file=sys.stderr)
        return 1
    if not args.ground_truth.is_dir():
        print(f"score: error: {args.ground_truth} is not a directory", file=sys.stderr)
        return 1
    score = scoring.score_results(results, args.ground_truth)
    sys.stdout.write(score.markdown() if args.markdown else score.table())
    if args.require_all_match and not score.all_match():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
