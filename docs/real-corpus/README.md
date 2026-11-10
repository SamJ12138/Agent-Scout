# Real-site corpus

| path | what it is | who writes it |
|---|---|---|
| `sites.yaml` | the real products the tool is run on | edited when the corpus changes |
| `ground-truth/<slug>.json` | a reference profile of each product, written from tool-mediated reads of its own site, in the project's ground-truth format | committed before the tool was run on these sites; method and limits in `ground-truth/README.md` |
| `results/latest.json` | the tool's `results.json` from the latest corpus run | the `corpus` workflow |
| `scores.md` | site status, and match / partial / mismatch / missing per site and field | the `corpus` workflow |
| `report.html` | the HTML report of that run | the `corpus` workflow |

Run it yourself (needs network access; a few minutes, because requests to one
host are spaced out):

    python scripts/run_corpus.py

The scoring rules are in `src/agent_scout/scoring.py`. The keyword tables in
`src/agent_scout/vocab.py` were committed before the ground-truth files were.
They were changed once after that, in the commit "fix: unknown instead of
wrong values on adversarial sentences", in response to a reviewer's test
sentences and not to this corpus.
