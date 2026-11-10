# Real-site corpus

| path | what it is | who writes it |
|---|---|---|
| `sites.yaml` | the real products the tool is run on | edited when the corpus changes |
| `ground-truth/<slug>.json` | a reference profile of each product, written from tool-mediated reads of its own site, in the project's ground-truth format | committed before the tool was run on these sites; method and limits in `ground-truth/README.md` |
| `results/latest.json` | the tool's `results.json` from the latest corpus run | the `corpus` workflow |
| `scores.md` | site status, and match / partial / mismatch / missing per site and field | the `corpus` workflow |
| `report.html` | the HTML report of that run | the `corpus` workflow |
| `run-1/scores.md` | the scores of the first run on real sites, before any rule was adjusted to them | kept unchanged |
| `run-2/scores.md` | the scores of the second run, after the rules had been adjusted using the first | kept unchanged |

Run it yourself (needs network access; a few minutes, because requests to one
host are spaced out):

    python scripts/run_corpus.py

The scoring rules are in `src/agent_scout/scoring.py`.

These scores are not a held-out test. The keyword tables in
`src/agent_scout/vocab.py` were committed before the ground-truth files were,
changed once for a reviewer's test sentences before any real run, and then
adjusted using the first real run (`run-1/scores.md`, kept as the before
figure) and again after the second (`run-2/scores.md`), which had produced a
wrong headquarters from the address of a hosting provider in a legal notice.
The project README lists the commits. The ground-truth files were not edited
to fit the tool.

## Known disagreements with the reference

The reference files are not edited after the fact. Where the tool and a
reference file disagree and the tool's quote is on the site, the case is
listed here and keeps counting as a mismatch in `scores.md`.

- relevance-ai / pricing (a mismatch in run 1 and in run 2). In run 2 the
  tool reports a free plan or trial and quotes "Get Started for free." from
  https://relevanceai.com/integrations. The reference says the pages read
  for it carry no free plan or trial wording; it did not read that page. No
  rule was changed for this case.
