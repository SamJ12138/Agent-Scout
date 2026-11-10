# Agent Scout real-site corpus: hand-made ground truth

Ten real products that sell AI agents or AI assistants for marketing work, with a hand-written
profile for each. The profiles were written by reading the products' own websites before anyone
looked at the tool's output. The annotator did not open the tool's code or results.

- Files: `sites.yaml` (name, url, slug, alphabetical by slug) and one `<slug>.json` per product.
- Format: `gm-ground-truth-schema.md` (fields, vocabularies, three-valued rules).
- `asOf`: 2026-11-10. Pages were read on 2026-11-09 and 2026-11-10.

## How the set was chosen

The goal was a small set that is global, mixed in size, and mixed in what the products do.

1. A candidate list was written from the annotator's general knowledge of the market: companies
   that describe themselves as AI agents, AI employees or AI assistants for content, email, ads,
   SEO, social, sales/CRM or e-commerce marketing.
2. Twelve candidate homepages were read. Ten were kept so that the set covers at least five
   countries, more than one kind of marketing work, and both agent products (they act) and
   generator or assistant products (they produce drafts). Two were read and dropped only to keep
   the count at ten and the spread wide: Artisan and Hypotenuse AI. Five more homepages were
   opened once just to see whether the reading tool could reach them (HubSpot Agent Hub, 11x,
   Lindy, Semrush, Typeface); none is in the corpus.
3. Size was not measured. The mix was chosen on expectation: Klaviyo and Jasper as larger
   vendors, the rest as smaller ones. What the pages read support: Klaviyo's about page lists
   offices in eight cities; SEO.AI's marketing site has two pages; Sintra's funding round was
   reported as a seed round (tech.eu, 10 June 2025). No headcount or revenue was looked up.

Three of the ten (neuroflash, Predis.ai, AdCreative.ai) call themselves AI content or ad
generators, not agents. They are in the set on purpose, so `can_execute` and `multi_agent` are
not all `true`.

## Country spread

| slug | product | country | city | where the location comes from |
|---|---|---|---|---|
| adcreative-ai | AdCreative.ai | France | Paris | own site (terms page mailing address; country word not printed) |
| jacquard | Jacquard | United Kingdom | London | own site (footer and contact page) |
| jasper | Jasper | United States | Austin | `hq_external` (mergr.com) |
| klaviyo | Klaviyo | United States | Boston | own site (about page; country word not printed) |
| madgicx | Madgicx | Israel | Tel Aviv | `hq_external` (peakspancapital.com portfolio page) |
| neuroflash | neuroflash | Germany | Hamburg | own site (legal notice) |
| predis-ai | Predis.ai | India | Pune | own site (`/llm-info/` page) |
| relevance-ai | Relevance AI | Australia | Sydney | `hq_external` (builtinsydney.au) |
| seo-ai | SEO.AI | Denmark | Kongens Lyngby | own site (footer) |
| sintra | Sintra | Lithuania | Vilnius | `hq_external` (tech.eu; weak, see below) |

Nine countries. `hq_external` is never used for scoring; it exists so this table can be written.
The Sintra entry is the weakest: the article calls it a Lithuanian startup that began in Vilnius
but does not say "headquarters", another directory lists offices in the United States and
Lithuania, and the legal entity on the site is PlayOS, Inc.

## Reading method and its limit

Each page was read with a web-fetch tool that downloads the page, converts it to text, and has a
language model answer a question about it. The annotator asked for word-for-word quotes: title,
meta description, hero headline and subhead, the sentences naming audiences and tasks, sentences
about acting versus drafting, sentences about agents working together, integration names, prices
as written, and any address line.

Limits a reader should know:

- **No markup was seen.** The tool returns text, not HTML. Whether a string sits in a `<meta>`
  tag, a heading, an `alt` attribute or JSON-LD is known only from what the tool said.
  `one_liner.kind` records what the tool called it.
- **Quotes pass through a model.** They were requested verbatim, and every `can_execute` and
  `multi_agent` quote was confirmed with a second, narrower read of the same page. Other quotes
  were read once. A character-level mismatch with the live page is possible.
- **The tool caps quotes at about 125 characters.** Longer sentences are recorded as their
  verbatim opening, and the field's `note` says so. Two meta descriptions (SEO.AI, Sintra) are
  recorded as their first sentence for this reason, and one (Relevance AI) was joined from two
  overlapping pieces.
- **Pages change.** Several sites showed dated promotions (Klaviyo's first-month price,
  AdCreative.ai's sale banner, Predis.ai's struck-through prices). Values are as of the read.
- **At most six pages per site, each read once** (plus the confirmation reads, which the tool
  serves from its cache). Anything stated only on a page that was not read is `unknown` here.
- Two very long pages were cut by the tool: the AdCreative.ai homepage (read to 100,000 of about
  102,000 characters, so its footer was lost) and the Relevance AI integrations directory (read to
  100,000 of about 344,000 characters).

## Annotation rules used

- Only the product's own site counts. `unknown` means the pages read do not say.
- A category, audience or task is listed only if a sentence or label on the site says it. Each
  listed value has a row in `evidence` with its page and quote. Where the support is a label
  and not a sentence, or the site's word was mapped to a vocabulary word (for example
  "advertisers" to `marketers`, "business owners" to `small business`, "large corporations" to
  `enterprise`), the field's `note` says so.
- `can_execute` is `true` when the site says the product itself publishes, sends, schedules,
  launches or books, even if a human approval step comes first. The note records the approval
  wording. No site in the set states that its product only drafts, so there is no `false`.
- `multi_agent` is `true` only for a sentence saying agents coordinate or hand off to each other.
  Klaviyo's heading "Your data, intelligence, and AI agents working as one" was re-read and left
  `unknown` because it describes one platform, not agents working together.
- `pricing.free_tier` is `true` for a free plan or a free trial. Only Klaviyo states a free plan;
  the other six `true` values are trials. Sintra is `false` because its pricing page says it does
  not offer free trials and lists no free plan.
- `pricing.starting_price` is the lowest per-month figure shown for a paid plan, whatever the
  billing term. Other figures a fair extractor could pick are in `also_acceptable`.
- `integrations` holds at most 25 names in page order. Names beyond 25 are in `overflow`.

## Keys beyond the schema

All optional, all ignorable by a scorer: `evidence` (per-value page and quote for list fields),
`note`, `kind` and `also_acceptable` (one_liner, pricing), `overflow` (integrations),
`confidence` (pricing, where the value is weak), `country_stated` (hq_location).

`country_stated: false` marks the two cases where the site prints a city and postcode but no
country word, and the country was derived from that address: Klaviyo ("Boston, MA 02111" gives
United States) and AdCreative.ai ("75004 PARIS" gives France). If the scorer should accept only
what is printed, treat the country in those two files as `unknown`.

## Sites a plain HTTP fetcher may struggle with

None of this could be tested. The shell in the annotation environment cannot reach websites, and
the reading tool got full text from all ten homepages. These are expectations, with the reason
for each.

| slug | expectation | why |
|---|---|---|
| klaviyo | Hardest in the set. Possible bot-protection refusal for a non-browser client; prices incomplete. | Large vendor site of the kind that often sits behind bot filtering (not verified here). Plan prices come from an interactive slider ("Select your number of active profiles"), so static HTML carries at most the default figures. |
| madgicx | Plan price missing. | The pricing page text has "See price inside the app." and a "$ 0 /mo" placeholder, which points to a price filled in by JavaScript. No address anywhere on the site. |
| relevance-ai | Integration list truncated or huge. | The directory page says "Showing 48 of 2,728 integrations" and runs to about 344,000 characters of text. The pricing page has no prices. |
| sintra | Integration names missing from the homepage; wrong price picked. | Homepage integrations are logo images whose names appear only in file names. Prices are shown next to higher list prices. |
| adcreative-ai | Wrong price picked; page size. | Three billing toggles are all in one long homepage (about 102,000 characters of text), with a sale banner and one internally inconsistent price. |
| jacquard | Possible bot check; single page. | The tool reported a Cloudflare Turnstile key on the page (on a form). Everything is on one long homepage with anchor links, and the page embeds prompts aimed at AI assistants inside its "Claude" and "ChatGPT" buttons. |
| predis-ai | Possible bot check; headquarters hard to find. | Email addresses came through as the placeholder Cloudflare's obfuscation leaves, so the site is probably served through Cloudflare. The headquarters line is only on `/llm-info/`, which normal navigation does not link. |

jasper, neuroflash and seo-ai are expected to be straightforward: full text came back for every
page and the facts sit in ordinary page copy.

## Known weaknesses of this corpus

- No `can_execute: false` case, so the scorer cannot test that branch on real sites.
- `hq_location` is `unknown` for four of ten sites (Jasper, Madgicx, Relevance AI, Sintra). For
  Relevance AI the terms page does say "an Australian business", which is a country but not a
  headquarters, and was left `unknown`.
- Two pricing values are weak and marked `confidence: low` (Madgicx, AdCreative.ai).
- Integration lists depend on which page is read. Predis.ai's own lists disagree with each other;
  neuroflash has an Integrations menu whose entries were not visible in the text reading.
- Category and task lists involve judgment. A scorer should not treat one extra or one missing
  list value as a serious error.
