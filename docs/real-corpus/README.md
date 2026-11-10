# Real-site corpus

| path | what it is | who writes it |
|---|---|---|
| `sites.yaml` | the real products the tool is run on | maintained by hand |
| `ground-truth/<slug>.json` | a profile of each product read from its own site, in the project's ground-truth format | written before the tool's output existed; method and limits in `ground-truth/README.md` |
| `results/latest.json` | the tool's `results.json` from the latest corpus run | the `corpus` workflow |
| `scores.md` | site status, and match / partial / mismatch / missing per site and field | the `corpus` workflow |
| `report.html` | the HTML report of that run | the `corpus` workflow |

Run it yourself (needs network access; a few minutes, because requests to one
host are spaced out):

    python scripts/run_corpus.py

The scoring rules are in `src/agent_scout/scoring.py`. The keyword tables in
`src/agent_scout/vocab.py` were committed before the ground-truth files were
opened by the author of the extractor.
