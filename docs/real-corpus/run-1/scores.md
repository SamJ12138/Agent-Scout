# Real-site corpus: scores

Written by `scripts/run_corpus.py` (GitHub Actions workflow `corpus`). Do not edit by hand.

- Run `20261110T141046Z-418b`, finished 2026-11-10T14:12:34Z, agent-scout 0.1.0
- Settings: rule-based extraction only (no LLM pass), 6 pages per site, 1.5 s between requests to one host, robots.txt honoured
- Sites read: 10 of 10 (read or partly read); the others are listed below with the reason
- Site-fields: 30 match, 43 partial, 4 mismatch, 13 missing, of 90

How to read this: the reference profiles in `ground-truth/` were written from tool-mediated reads of each product's own site and committed before the tool was run on these sites (see `ground-truth/README.md` for the method and its limits). `match`, `partial`, `mismatch` and `missing` are defined in `src/agent_scout/scoring.py`. A site the tool could not read has every field unknown, so each field the reference knows counts as `missing` there: those rows measure reachability, not extraction. The corpus has no product whose site says it only drafts, so nothing here tests `can_execute: false`. Category and task lists involve judgment; one extra or one absent list value makes a field `partial`.

## Site status

| site | status | detail | pages read |
|---|---|---|---|
| adcreative-ai | read | 6 pages read | 6 |
| jacquard | read | 3 pages read | 3 |
| jasper | read | 6 pages read | 6 |
| klaviyo | read | 6 pages read | 6 |
| madgicx | read | 6 pages read | 6 |
| neuroflash | read | 6 pages read | 6 |
| predis-ai | read | 4 pages read | 4 |
| relevance-ai | read | 6 pages read | 6 |
| seo-ai | read | 6 pages read | 6 |
| sintra | read | 6 pages read | 6 |

## Per site and field

| site | status | one_liner | categories | target_user | tasks | can_execute | multi_agent | integrations | pricing | hq_location |
|---|---|---|---|---|---|---|---|---|---|---|
| adcreative-ai | ok | match | partial | partial | partial | mismatch | match | missing | partial | missing |
| jacquard | ok | match | partial | partial | partial | match | missing | partial | match | match |
| jasper | ok | match | partial | partial | partial | match | missing | partial | match | match |
| klaviyo | ok | partial | partial | partial | partial | match | match | partial | match | match |
| madgicx | ok | partial | partial | partial | partial | match | match | missing | partial | match |
| neuroflash | ok | match | match | partial | partial | match | match | missing | partial | missing |
| predis-ai | ok | match | partial | partial | partial | missing | match | partial | partial | match |
| relevance-ai | ok | match | partial | partial | partial | missing | match | mismatch | mismatch | match |
| seo-ai | ok | partial | partial | partial | partial | match | match | missing | partial | missing |
| sintra | ok | partial | partial | partial | partial | missing | missing | partial | mismatch | match |

| field | match | partial | mismatch | missing |
|---|---|---|---|---|
| one_liner | 6 | 4 | 0 | 0 |
| categories | 1 | 9 | 0 | 0 |
| target_user | 0 | 10 | 0 | 0 |
| tasks | 0 | 10 | 0 | 0 |
| can_execute | 6 | 0 | 1 | 3 |
| multi_agent | 7 | 0 | 0 | 3 |
| integrations | 0 | 5 | 1 | 4 |
| pricing | 3 | 5 | 2 | 0 |
| hq_location | 7 | 0 | 0 | 3 |

Totals: 30 match, 43 partial, 4 mismatch, 13 missing (of 90 site-fields).

Details:
- adcreative-ai / categories: partial (2 of 3 found, 3 extra)
- adcreative-ai / target_user: partial (5 of 5 found, 1 extra)
- adcreative-ai / tasks: partial (3 of 4 found, 5 extra)
- adcreative-ai / can_execute: mismatch (reference says the site does not state this)
- adcreative-ai / pricing: partial (differs: starting_price)
- jacquard / categories: partial (1 of 2 found, 1 extra)
- jacquard / target_user: partial (1 of 1 found, 1 extra)
- jacquard / tasks: partial (2 of 3 found, 2 extra)
- jacquard / integrations: partial (3 of 14 found, 0 extra)
- jasper / categories: partial (3 of 3 found, 4 extra)
- jasper / target_user: partial (2 of 2 found, 3 extra)
- jasper / tasks: partial (6 of 7 found, 2 extra)
- jasper / integrations: partial (12 of 18 found, 4 extra)
- klaviyo / one_liner: partial (word overlap 0.56)
- klaviyo / categories: partial (4 of 4 found, 1 extra)
- klaviyo / target_user: partial (2 of 5 found, 1 extra)
- klaviyo / tasks: partial (3 of 6 found, 0 extra)
- klaviyo / integrations: partial (15 of 23 found, 4 extra)
- madgicx / one_liner: partial (word overlap 0.61)
- madgicx / categories: partial (2 of 2 found, 1 extra)
- madgicx / target_user: partial (1 of 2 found, 1 extra)
- madgicx / tasks: partial (2 of 3 found, 1 extra)
- madgicx / pricing: partial (differs: starting_price)
- neuroflash / target_user: partial (3 of 3 found, 1 extra)
- neuroflash / tasks: partial (4 of 4 found, 2 extra)
- neuroflash / pricing: partial (differs: starting_price)
- predis-ai / categories: partial (3 of 3 found, 2 extra)
- predis-ai / target_user: partial (2 of 3 found, 2 extra)
- predis-ai / tasks: partial (5 of 5 found, 1 extra)
- predis-ai / integrations: partial (1 of 12 found, 2 extra)
- predis-ai / pricing: partial (differs: starting_price)
- relevance-ai / categories: partial (2 of 3 found, 1 extra)
- relevance-ai / target_user: partial (3 of 4 found, 0 extra)
- relevance-ai / tasks: partial (4 of 5 found, 1 extra)
- relevance-ai / integrations: mismatch (0 of 25 found, 25 extra)
- relevance-ai / pricing: mismatch (reference says the site does not state this)
- seo-ai / one_liner: partial (word overlap 0.48)
- seo-ai / categories: partial (2 of 2 found, 2 extra)
- seo-ai / target_user: partial (1 of 2 found, 5 extra)
- seo-ai / tasks: partial (2 of 2 found, 2 extra)
- seo-ai / pricing: partial (differs: starting_price)
- sintra / one_liner: partial (word overlap 0.73)
- sintra / categories: partial (8 of 8 found, 3 extra)
- sintra / target_user: partial (2 of 2 found, 4 extra)
- sintra / tasks: partial (7 of 7 found, 5 extra)
- sintra / integrations: partial (21 of 25 found, 0 extra)
- sintra / pricing: mismatch (differs: free_tier, starting_price)

## Fields on sites that were read

The same counts restricted to sites with status read or partly read.

| field | match | partial | mismatch | missing |
|---|---|---|---|---|
| one_liner | 6 | 4 | 0 | 0 |
| categories | 1 | 9 | 0 | 0 |
| target_user | 0 | 10 | 0 | 0 |
| tasks | 0 | 10 | 0 | 0 |
| can_execute | 6 | 0 | 1 | 3 |
| multi_agent | 7 | 0 | 0 | 3 |
| integrations | 0 | 5 | 1 | 4 |
| pricing | 3 | 5 | 2 | 0 |
| hq_location | 7 | 0 | 0 | 3 |

Sites in this second table: 10.
