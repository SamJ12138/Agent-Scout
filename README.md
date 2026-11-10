# Agent Scout

![The tool running in a terminal on six sample sites, then its HTML report: comparison table, a product profile with quoted evidence, and a blocked site](docs/demo.gif)

*What is shown: the real console output of the tool run on the six bundled
fictional sample sites (pauses between requests shortened), then the report of
that run. Rendered by `scripts/make_demo_video.py`; nothing was recorded by
hand. Full quality: [docs/demo.mp4](docs/demo.mp4) (32 seconds).*

Agent Scout is a command-line researcher for one narrow job: profiling AI
marketing-agent products from their own public websites. You give it a list
of product URLs. For each product it reads a handful of pages (politely) and
writes a structured profile: what the product does, who it is for, whether it
acts by itself or only drafts, what it integrates with, what it costs and
where the company is. Every value in that profile carries its evidence: the
URL of the page and the sentence, heading, table row or tag it was read from.
Anything the site does not state is reported as `unknown`.

Evidence per field is the point. Vendor comparisons are usually filled in from
memory or from a model's guess, and a wrong cell looks exactly like a right
one. Here a reader can check any cell against the quoted sentence in a few
seconds, and an empty cell means "the site does not say", never "no".

## Quickstart without network access

The repository bundles six invented product websites (every name ends in
"(fictional)"). `scripts/demo.py` serves them on `127.0.0.1`, runs the tool on
them and prints where the reports are. Nothing outside your machine is
contacted and nothing is opened. Python 3.10 or newer.

PowerShell:

```powershell
git clone https://github.com/SamJ12138/agent-scout.git
cd agent-scout
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts\demo.py
```

bash:

```bash
git clone https://github.com/SamJ12138/agent-scout.git
cd agent-scout
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/demo.py
```

It takes about ten seconds and ends with

```
Reports: demo-output/reports/results.json, demo-output/reports/results.csv, demo-output/reports/report.md, demo-output/reports/report.html
Log:     demo-output/logs/run_<id>.jsonl

Open demo-output/reports/report.html in a browser.
```

The six sample sites are there to show every outcome: three ordinary sites,
one JavaScript shell (reported as partly read), one that answers 403 to
everything (reported as blocked) and one whose robots.txt is broken (reported
as ruled out). Add `--keep-serving` if you want the source links in the report
to open.

## Running it on real sites

Write the sites into a YAML file, or one URL per line into a text file:

```yaml
# sites.yaml
- name: Example Product      # optional
  url: https://www.example.com/
- https://another.example/
```

```bash
agent-scout run sites.yaml -o out
agent-scout report-log logs/run_<id>.jsonl    # error counts and stage timings of that run
```

| option | default | meaning |
|---|---|---|
| `-o`, `--out` | `out` | directory for the four report files |
| `--config FILE` | none | YAML settings, see `config.example.yaml` |
| `--page-budget N` | 6 | pages read per site, homepage included |
| `--delay S` | 1.5 | seconds between two requests to the same host |
| `--timeout S` | 20 | seconds per request |
| `--log-dir DIR` | `logs` | where `run_<id>.jsonl` is written |
| `--quiet` | off | print errors only |
| `--llm` | off | add the optional LLM pass (see below) |

Exit codes: `0` the run finished (a blocked or unreachable site is a result,
not an error); `1` an error, reported as one line on stderr; `2` a usage
error.

Output files:

- `results.json`: everything, including the page log of each site. The schema
  (version 1.0) is documented at the top of `src/agent_scout/pipeline.py`.
- `results.csv`: one row per site, with the first source URL and quote of
  each field.
- `report.md`: the comparison and every profile with its quotes.
- `report.html`: one self-contained file (inline CSS and JavaScript, no
  external request): a summary, how many reachable sites state each field, a
  comparison table with category and country filters, and a profile per
  product in which each value sits next to its quote and a link to the page.
  Sites that could not be read are hatched and say why.

## How it fetches

- It identifies itself honestly:
  `agent-scout/<version> (+https://github.com/SamJ12138/agent-scout)`.
- It reads `robots.txt` first and follows [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html):
  the group naming `agent-scout` is used if there is one, otherwise `*`; the
  longest matching rule wins; a 4xx answer for robots.txt means no
  restrictions; a 5xx answer or a network failure rules the whole site out for
  that run. `Crawl-delay` is honoured, and a site asking for more than
  `max_crawl_delay_seconds` (30) is skipped.
- Requests to one host are at least `max(--delay, Crawl-delay)` apart.
- It reads at most six pages per site: the homepage, then same-site pages
  picked from the homepage's links, one per topic in this order: features /
  product / platform, integrations, pricing, about / company, contact,
  customers.
- It advertises only the content encodings it can decode (gzip, deflate, br)
  and decodes bodies itself. A body it cannot decode is a fetch error, never a
  page.
- One retry on 5xx or 429, with `Retry-After` honoured up to 30 seconds.
- It makes no attempt to get around bot protection. A 401, 403 or 429, or a
  challenge page, ends that site with status `blocked`.
- A page with almost no visible text that loads scripts is flagged
  `needs_rendering`. Only its head data (meta description, JSON-LD) is used.
  There is no JavaScript rendering option.

Site status is one of:

| status | shown as | meaning |
|---|---|---|
| `ok` | read | every requested page was read |
| `partial` | partly read | the homepage was read, but a page failed or is a JavaScript shell |
| `blocked` | blocked | 401 / 403 / 429 or a challenge page, on any page; every field is unknown |
| `unreachable` | unreachable | the start URL could not be fetched; every field is unknown |
| `robots_disallowed` | ruled out by robots.txt | robots.txt forbids the start URL or could not be read; every field is unknown |

## Fields

Everything is about what the product's own site says. Nothing comes from
third-party sites.

| field | value | meaning |
|---|---|---|
| `one_liner` | text | the site's own short description: meta description, else og:description, else JSON-LD description, else the first heading and the sentence after it |
| `categories` | list from a fixed vocabulary | what kind of marketing work the product does |
| `target_user` | list from a fixed vocabulary | audiences the site names |
| `tasks` | list from a fixed vocabulary | tasks the site says the product performs |
| `can_execute` | true / false / unknown | true only if the site states the product itself acts in other systems or channels (sends, publishes, schedules, launches or adjusts campaigns, updates a CRM); false only if the site states it only drafts or suggests; otherwise unknown. If the site says both, unknown |
| `multi_agent` | true / unknown | true if the site states several agents work together. Never false |
| `integrations` | list of names, at most 25 | third-party products named as integrations |
| `pricing` | `free_tier` true / false / unknown, `starting_price` as written | a free plan or trial is stated; the lowest paid price exactly as the site writes it |
| `hq_location` | `city`, `country` | the company address or headquarters as the site states it (JSON-LD, `<address>`, a "headquartered in" sentence, a footer address) |

Vocabularies:

- categories: content generation, email marketing, advertising, seo, social
  media, sales & crm, analytics & reporting, customer support, ecommerce,
  video & creative, general agent platform
- target_user: marketers, ecommerce brands, agencies, enterprise, small
  business, developers, sales teams, creators
- tasks: write copy, generate images or video, send email campaigns, manage
  ads, seo optimization, schedule social posts, lead qualification, customer
  chat, analytics reporting, workflow automation, personalization, market
  research

Each piece of evidence records a `method`: `meta`, `json-ld`, `heading`,
`sentence`, `link` (link text or a logo's alt text), `table` (the cells of one
row joined with ` | `), or `llm`.

How values are decided: the extraction is rule-based. All keyword tables live
in one file, `src/agent_scout/vocab.py`, and each entry has an example
sentence in `tests/test_vocab.py`. A phrase preceded by a negation in the same
sentence ("is not an SEO tool") is ignored. Navigation, footers, table rows
and lists of integrations are not read as statements about the product. A
category needs a hit in a heading or meta description, or two separate
sentences; audiences and tasks are reported when stated once.

## Optional LLM pass

Off unless you pass `--llm`; the config file cannot switch it on.

```bash
export AGENT_SCOUT_LLM_API_KEY=...            # PowerShell: $env:AGENT_SCOUT_LLM_API_KEY = "..."
agent-scout run sites.yaml --llm --llm-provider openai-compatible \
    --llm-base-url https://api.deepseek.com --llm-model <model name>
agent-scout run sites.yaml --llm --llm-provider anthropic --llm-model <model name>
```

- `openai-compatible` posts to `<base URL>/chat/completions` with a Bearer
  key. DeepSeek's documentation says "The DeepSeek API uses an API format
  compatible with OpenAI/Anthropic" and gives `https://api.deepseek.com` as
  the base URL for the OpenAI format
  ([api-docs.deepseek.com](https://api-docs.deepseek.com/)).
- `anthropic` posts to `https://api.anthropic.com/v1/messages` with the
  `x-api-key` and `anthropic-version` headers. The version sent is the setting
  `llm.anthropic_version` (default `2023-06-01`).
- Provider, base URL and model can also come from `AGENT_SCOUT_LLM_PROVIDER`,
  `AGENT_SCOUT_LLM_BASE_URL`, `AGENT_SCOUT_LLM_MODEL` or the `llm:` section of
  the config file. The key is read from the environment only and is never
  written to logs, reports or error messages.

What leaves your machine: for each site that was read, the cleaned text of the
pages the tool fetched (title, meta description, visible text; up to 24,000
characters per site) and the fixed instructions. No raw HTML, no page that
robots.txt disallowed, nothing about blocked sites, nothing about you.

What comes back is not trusted. The model must give a verbatim quote for every
value, and a validator drops any value whose quote is not found in the fetched
text (compared after normalising whitespace and case), any value outside the
vocabularies, a `multi_agent: false`, and any integration name, price or city
that does not appear in its own quote. Survivors are added with
`method: llm`; they never replace a rule-based value. The validator proves the
quote is on the page. It does not prove the quote supports the value, which is
why the quote is shown.

A web page can contain text addressed to language models. The prompt marks
page text as untrusted data, and the validator limits what such text can
achieve to values that quote the page itself.

**This pass has not been run against a live model.** There was no API key in
the environment where it was written. It is tested against a fake transport
(success, 401, 429 with one retry, timeout, malformed output, a hallucinated
quote being dropped), so the request shapes follow the providers'
documentation but are unverified in practice.

## Accuracy

Two different things are measured, and they should not be confused.

**Fixture gate (a regression test, not an accuracy claim).** For the six
bundled fictional sites there is a ground-truth file each, written from the
HTML before the extractor was run on it. The suite requires every field of
every site to match:

```
site        status            one_liner  categories target     tasks      executes   multi      integr     pricing    hq
northwind   ok                match      match      match      match      match      match      match      match      match
quillmate   ok                match      match      match      match      match      match      match      match      match
orbitfleet  ok                match      match      match      match      match      match      match      match      match
glimmer     partial           match      match      match      match      match      match      match      match      match
palisade    blocked           match      match      match      match      match      match      match      match      match
tessera     robots_disallowed match      match      match      match      match      match      match      match      match

totals: 54 match, 0 partial, 0 mismatch, 0 missing (of 54 site-fields)
```

The sites, the ground truth and the keyword tables have the same author, so
54 of 54 says the pipeline does what it was built to do on pages written with
it in mind. It says nothing about real websites. The three unread sites match
because both sides are all `unknown`.

**Real-site corpus.** `docs/real-corpus/` holds a list of ten real products
and a ground-truth profile for each, written by reading the products' own
sites before the tool's output existed (method and limits:
`docs/real-corpus/ground-truth/README.md`). The keyword tables were committed
before those files were opened. The scores are produced by the `corpus`
GitHub Actions workflow, which runs the tool with default settings on those
sites and commits the result to
[`docs/real-corpus/scores.md`](docs/real-corpus/scores.md), next to the raw
results and the HTML report of that run. The environment in which the tool was
written could not reach public websites, so there is no real-site number in
this README: read `scores.md`. Expect it to be much less flattering than the
fixture gate, with whole rows missing wherever a site blocks an unknown
crawler.

Scoring rules (`src/agent_scout/scoring.py`): `match` equal after
normalisation, both `unknown` included; `partial` lists that overlap but
differ, a one-liner that contains or mostly overlaps the reference, one right
pricing sub-value, right country with a different city; `mismatch` a stated
value that does not agree, including a value where the reference says the
site does not state one; `missing` the reference has a value and the tool
says `unknown`.

```bash
python scripts/score.py out/results.json path/to/ground-truth    # score any run
python scripts/run_corpus.py                                     # the real-site corpus (needs network)
```

## Run log

Every run writes `logs/run_<id>.jsonl`, one JSON object per event:
`ts`, `run_id`, `site`, `stage` (input, robots, fetch, parse, extract, llm,
report, run), `event` (start, success, fail, skip), `duration_ms`,
`error_type`, `context`. Every request is logged with URL, status, bytes and
content encoding; every extracted field with the methods used.
`agent-scout report-log FILE` prints failure and skip counts by stage and
error type, and p50 / p95 durations per stage.

## Development

```bash
python -m pip install -e . -r requirements-dev.txt
python -m pytest                      # about 20 seconds
python scripts/install_hooks.py       # optional: run the suite before every commit
```

The suite makes no request to the internet: every HTTP request in it goes to
a server it starts on `127.0.0.1`. A test fails if an `except` block in the
package has no log call, if a keyword-table entry has no example, if a
declared dependency is unused or an import undeclared, or if a tracked file
contains personal data. Two report tests need Chromium through Playwright
and one video test needs ffmpeg; they are skipped where those are not
installed, and Chromium is not installed in CI. CI runs the suite on the
`ubuntu-24.04` and `windows-2025` runners with Python 3.12.

The demo video is rendered by a script, so it can be regenerated after a
change (needs ffmpeg on PATH and Chromium for Playwright):

```bash
python -m playwright install chromium        # once
python scripts/make_demo_video.py            # writes docs/demo.mp4 and docs/demo.gif, about a minute
python scripts/make_demo_video.py --report docs/real-corpus/report.html --label "Real-site corpus run"
```

The second form films another report in the middle scene, under a caption you
supply; the terminal scene always shows the bundled sample sites and says so.

Layout:

```
src/agent_scout/   cli, config, inputs, robots, fetch, page, links, crawl,
                   vocab, textmatch, geo, extract, llm, pipeline, reports,
                   scoring, obs
scripts/           demo.py, score.py, run_corpus.py, fixture_server.py,
                   make_demo_video.py, install_hooks.py, hooks/pre-commit
tests/             the suite; fixtures/sites (fictional sites) and
                   fixtures/ground-truth
docs/real-corpus/  real-site list, ground truth, and the workflow's outputs
```

## Limitations

- The vocabulary fields come from keyword rules. They miss paraphrases and
  can misread a sentence. The quote next to each value is there so that you
  can see what it rests on.
- English only.
- No JavaScript rendering. Sites that build their content in the browser are
  flagged and mostly `unknown`.
- Six pages per site by default. A fact on a page the tool did not pick (a
  legal notice, a deep pricing page) is not found.
- A 401, 403 or 429 on any page ends the site as `blocked` and discards what
  was read before it. That is deliberate and conservative.
- Prices are recognised with the currency symbol in front (`$49`, `€12`,
  `£29`). `42€`, prices set by a slider or filled in by scripts, and prices
  in other currencies are not. The "lowest price" can be an add-on or a
  promotional figure if that is the lowest number on the pricing page.
- Headquarters: the country is reported only when the site names it, gives an
  ISO code in JSON-LD, or names a US state. About 65 countries are
  recognised. A postcode alone does not yield a country.
- Integrations: names are taken from logo alt texts ending in "logo" or
  "icon", from a list of about 90 known product names, and from sentences
  such as "integrates with A, B and C". Logo walls without alt text and
  directories of thousands of apps are covered poorly.
- The LLM pass is untested against a live model (see above).
- Sites are read one after another. This is a tool for a list of tens of
  products, not a crawler.

## License

MIT. Copyright 2026 Tianyi Jia. See [LICENSE](LICENSE).
