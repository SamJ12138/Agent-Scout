"""Rule-based extraction of every schema field from the pages of one site.

Each function returns a FieldResult: a value (or "unknown") plus the evidence
it rests on (page URL, verbatim quote, method). Nothing is inferred beyond
what a quote states; a field no page states stays "unknown". When a rule
cannot tell whether a sentence makes a claim about the product, the answer is
"unknown": a wrong true or false is worse than a missing value.

What is read: text in the page's main content and header. Navigation,
customer quotes (blockquotes, testimonial blocks), consent banners and, except
for the company address, footers are not the site describing its product and
are never read. From a page flagged ``needs_rendering`` only head data is used
(meta tags for the one-liner, JSON-LD for address and offers).
"""

from __future__ import annotations

import json
import re
from typing import Iterator
from urllib.parse import urlsplit

from . import obs
from .config import Config
from .geo import country_name, parse_place, states_the_united_states
from .model import FIELDS, UNKNOWN, Evidence, FieldResult, unknown_fields
from .page import Page, Snippet, split_sentences
from .textmatch import (find_all, find_phrase, has_phrase, is_rhetorical, normalise_quotes, phrase_regex,
                        preceded_by, words_before)
from .vocab import (AGENT_SUBJECTS, ASSIST_WORDS, AUDIENCE_COMPARISON_WINDOW, AUDIENCE_COMPARISONS,
                    AUTONOMY_MARKERS, CATEGORIES, CONSENT_HEADING_WORDS, DRAFT_ONLY_PHRASES, DRAFT_ONLY_VERBS,
                    EXECUTE_OBJECTS, EXECUTE_VERBS, FREE_TIER_PHRASES, GENERAL_OBJECTS, HQ_CUES,
                    INTEGRATION_TRIGGERS, KNOWN_INTEGRATIONS, LOGO_SUFFIXES, MULTI_AGENT_PHRASES, NEGATORS,
                    FREE_NOUNS, NOT_A_CITY, NOT_A_FREE_PLAN, NOT_AVAILABLE, NOT_A_PRICE_AFTER, NOT_A_PRICE_BEFORE, NOT_A_PRICE_WINDOW,
                    NOT_A_PRODUCT, OFFER_NEGATIONS, OFFER_VERBS, PRICE_CUES, SELF_MARKERS, STRONG_HIT, TARGET_USERS, TASKS, THIRD_PARTIES,
                    THRESHOLDS, USER_SUBJECT_WINDOW, USER_SUBJECTS, WEAK_HIT)

VOCAB_TABLES = {"categories": CATEGORIES, "target_user": TARGET_USERS, "tasks": TASKS}
DESCRIBING_TYPES = {"SoftwareApplication", "WebApplication", "Product", "Organization", "Corporation",
                    "WebSite", "Service"}
MAX_ONE_LINER_CHARS = 300


def _types(obj: dict) -> set[str]:
    """The schema.org types of a JSON-LD object (a string or a list in the wild)."""
    kinds = obj.get("@type")
    return {kind for kind in (kinds if isinstance(kinds, list) else [kinds]) if isinstance(kind, str)}


def _readable(pages: list[Page]) -> list[Page]:
    return [page for page in pages if not page.needs_rendering]


SPEAKING_ZONES = ("main", "header")      # where the site itself describes its product


def _spoken(page: Page, methods: tuple[str, ...] = ("heading", "sentence")) -> list[Snippet]:
    """Snippets of a page in which the site speaks about its product."""
    return [s for s in page.snippets if s.zone in SPEAKING_ZONES and s.method in methods]


def _statements(pages: list[Page]) -> Iterator[tuple[Page, Snippet]]:
    """What the site says about the product: head descriptions, headings and
    sentences of the main content. Navigation, footers, customer quotes,
    consent banners, link-only text, table rows and anything presented as a
    list of integrations are left out, and a text repeated across pages is
    yielded once."""
    seen: set[str] = set()
    for page in _readable(pages):
        if page.topic == "integrations":
            continue
        head = [page.meta.get("description"), page.meta.get("og:description"), page.title]
        candidates = [Snippet(text, "meta", "head") for text in head if text]
        candidates += [s for s in _spoken(page) if not s.in_integration_section]
        for snippet in candidates:
            key = snippet.text.lower()
            if key not in seen:
                seen.add(key)
                yield page, snippet


# --------------------------------------------------------------------------- one_liner
def _trim(text: str) -> str:
    if len(text) <= MAX_ONE_LINER_CHARS:
        return text
    kept = ""
    for sentence in split_sentences(text):
        if len(kept) + len(sentence) + 1 > MAX_ONE_LINER_CHARS:
            break
        kept = f"{kept} {sentence}".strip()
    return kept or text[:MAX_ONE_LINER_CHARS].rsplit(" ", 1)[0]


def extract_one_liner(pages: list[Page]) -> FieldResult:
    if not pages:
        return FieldResult()
    home = pages[0]
    for key in ("description", "og:description", "twitter:description"):
        if home.meta.get(key):
            text = _trim(home.meta[key])
            return FieldResult(text, [Evidence(home.url, text, "meta")])
    for obj in home.json_ld:
        if _types(obj) & DESCRIBING_TYPES and isinstance(obj.get("description"), str) and obj["description"].strip():
            text = _trim(" ".join(obj["description"].split()))
            return FieldResult(text, [Evidence(home.url, text, "json-ld")])
    if home.needs_rendering:
        return FieldResult()
    # Hero: the first <h1> (else the first heading) and the sentence right after it.
    body = [s for s in _spoken(home) if not (s.method == "heading" and has_phrase(s.text, CONSENT_HEADING_WORDS))]
    headings = [index for index, snippet in enumerate(body) if snippet.method == "heading"]
    first_h1 = next((index for index in headings if body[index].level == 1), None)
    start = first_h1 if first_h1 is not None else (headings[0] if headings else None)
    if start is None or start + 1 >= len(body) or body[start + 1].method != "sentence":
        return FieldResult()
    heading, following = body[start], body[start + 1]
    joiner = " " if heading.text[-1] in ".!?:" else ": "
    return FieldResult(_trim(f"{heading.text}{joiner}{following.text}"),
                       [Evidence(home.url, heading.text, "heading"),
                        Evidence(home.url, following.text, "sentence")])


# --------------------------------------------------------------------------- vocabulary fields
def extract_vocab(pages: list[Page], field: str) -> FieldResult:
    """categories / target_user / tasks: labels whose phrases the site uses."""
    table = VOCAB_TABLES[field]
    scores: dict[str, int] = {}
    evidence: dict[str, tuple[int, Evidence]] = {}
    for page, snippet in _statements(pages):
        weight = STRONG_HIT if snippet.method in ("meta", "heading") else WEAK_HIT
        for label, phrases in table.items():
            matches = find_all(snippet.text, phrases)
            if field == "target_user":           # "cheaper than an agency" names no audience
                matches = [m for m in matches if not preceded_by(snippet.text, m.start(), AUDIENCE_COMPARISONS,
                                                                 AUDIENCE_COMPARISON_WINDOW)]
            if not matches:
                continue
            scores[label] = scores.get(label, 0) + weight
            if label not in evidence or weight > evidence[label][0]:
                evidence[label] = (weight, Evidence(page.url, snippet.text, snippet.method, item=label))
    values = [label for label in table if scores.get(label, 0) >= THRESHOLDS[field]]
    if not values:
        return FieldResult()
    return FieldResult(values, [evidence[label][1] for label in values])


# --------------------------------------------------------------------------- can_execute / multi_agent
def _states_execution(text: str) -> bool:
    """The sentence says the product itself acts in another system or channel."""
    if is_rhetorical(text):
        return False
    objects = find_all(text, EXECUTE_OBJECTS)
    autonomous = has_phrase(text, AUTONOMY_MARKERS)
    for verb in find_all(text, EXECUTE_VERBS):
        if not any(obj.end() <= verb.start() or obj.start() >= verb.end() for obj in objects):
            continue                                   # the verb needs an object of its own
        before = text[:verb.start()]
        if re.search(r"\bto[\s-]+$", before):
            continue                                   # "ready-to-launch", "to send": a purpose, not an act
        if has_phrase(before, ASSIST_WORDS):
            continue                                   # "helps you launch", "drafts ... to post"
        if set(words_before(text, verb.start(), USER_SUBJECT_WINDOW)) & set(USER_SUBJECTS):
            continue                                   # "for you to send", "so you can publish": the person acts
        if autonomous or has_phrase(before, AGENT_SUBJECTS):
            return True
    return False


def _alternatives(words) -> str:
    return "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in sorted(words, key=len, reverse=True))


_NEGATED_ACTION = re.compile(
    rf"(?<![\w'])(?:{_alternatives(NEGATORS)})\s+(?:{_alternatives(DRAFT_ONLY_VERBS)})(?:e?s)?"
    rf"(?:\s*(?:,|or|and|nor)\s*(?:{_alternatives(DRAFT_ONLY_VERBS)})(?:e?s)?)*(?![\w'])", re.IGNORECASE)
_GENERAL_TAIL = re.compile(
    rf"(?:\s+(?:any|your|the))?(?:\s+(?:{_alternatives(GENERAL_OBJECTS)}))?"
    rf"(?:\s+(?:{_alternatives(SELF_MARKERS)}))?\s*(?:[.,;:!?]|$)", re.IGNORECASE)


def _states_draft_only(text: str) -> bool:
    """The sentence says, without qualification, that the product does not act."""
    if has_phrase(text, DRAFT_ONLY_PHRASES):
        return True
    text = normalise_quotes(text)
    for action in _NEGATED_ACTION.finditer(text):
        if set(words_before(text, action.start(), USER_SUBJECT_WINDOW)) & set(USER_SUBJECTS):
            continue                                   # "you never send ..." is about the person
        if _GENERAL_TAIL.match(text, action.end()):
            return True
    return False


def extract_can_execute(pages: list[Page], site: str | None = None) -> FieldResult:
    acts: Evidence | None = None
    drafts: Evidence | None = None
    for page, snippet in _statements(pages):
        if _states_draft_only(snippet.text):
            drafts = drafts or Evidence(page.url, snippet.text, snippet.method)
        elif _states_execution(snippet.text):
            acts = acts or Evidence(page.url, snippet.text, snippet.method)
    if acts and drafts:
        obs.emit("extract", "skip", site=site, error_type="conflicting_statements", field="can_execute",
                 acts=acts.quote, drafts=drafts.quote)
        return FieldResult()
    if acts:
        return FieldResult(True, [acts])
    if drafts:
        return FieldResult(False, [drafts])
    return FieldResult()


def extract_multi_agent(pages: list[Page]) -> FieldResult:
    for page, snippet in _statements(pages):
        if not is_rhetorical(snippet.text) and has_phrase(snippet.text, MULTI_AGENT_PHRASES):
            return FieldResult(True, [Evidence(page.url, snippet.text, snippet.method)])
    return FieldResult()


# --------------------------------------------------------------------------- integrations
_KNOWN_LOOKUP = {spelling.lower(): name for name, aliases in KNOWN_INTEGRATIONS.items()
                 for spelling in (name, *aliases)}
_SUFFIX = re.compile(r"\s+(?:" + "|".join(LOGO_SUFFIXES) + r")s?$", re.IGNORECASE)


def _strip_suffix(text: str) -> tuple[str, bool]:
    stripped = _SUFFIX.sub("", text.strip())
    return stripped, stripped != text.strip()


def known_integration(text: str) -> str | None:
    """Canonical name when ``text`` (optionally followed by 'logo') is a known product."""
    name, _ = _strip_suffix(text)
    return _KNOWN_LOOKUP.get(name.strip().lower())


def _plausible_name(name: str) -> bool:
    words = name.split()
    return (0 < len(words) <= 4 and len(name) <= 40 and name[0].isalnum()
            and (name[0].isupper() or name[0].isdigit())
            and words[0].lower() not in NOT_A_PRODUCT and name.lower() not in NOT_A_PRODUCT)


def _names_after_trigger(rest: str) -> list[str]:
    """'Instagram, LinkedIn and Slack to keep ...' -> the product names.

    A name outside the known list is only kept when the same list also names
    a known product: "Works with Marketing Teams" lists no product at all.
    """
    rest = re.split(r"[.;:!?(]\s|[.;:!?]$", rest, maxsplit=1)[0]
    names: list[tuple[str, bool]] = []
    for token in re.split(r",|\band\b|&|\bor\b|\bplus\b", rest):
        run: list[str] = []
        for word in token.strip().strip(".").split():
            if (word[0].isupper() or word[0].isdigit()) and len(run) < 3:
                run.append(word.rstrip(".,"))
            else:
                break
        full = " ".join(run)
        while run:
            canonical = _KNOWN_LOOKUP.get(" ".join(run).lower())
            if canonical:
                names.append((" ".join(run), True))        # as the site writes it
                break
            run.pop()
        if not run and full and _plausible_name(full):
            names.append((full, False))
    if not any(known for _, known in names):
        return []
    return [name for name, _ in names]


def _is_integration_page(page: Page) -> bool:
    return page.topic == "integrations" or bool(re.search(r"integrat|connector", urlsplit(page.url).path.lower()))


MAX_INTEGRATION_CANDIDATES = 2000     # how many names are considered before the limit is applied


def _as_written(text: str) -> tuple[str, str] | None:
    """(name to report, canonical key) for a known product, else None. The
    site's own spelling is kept ("Google BigQuery", "Google Analytics 4");
    only letter case is taken from the known list."""
    name, _ = _strip_suffix(text)
    canonical = _KNOWN_LOOKUP.get(name.strip().lower())
    if canonical is None:
        return None
    return (canonical if name.strip().lower() == canonical.lower() else name.strip()), canonical.lower()


def extract_integrations(pages: list[Page], site_name: str | None, limit: int) -> FieldResult:
    found: dict[str, tuple[Evidence, bool]] = {}          # key -> (evidence, is a known product)
    own = {word.lower() for word in re.findall(r"\w+", site_name or "")}

    def add(name: str, page: Page, quote: str, method: str, key: str | None = None) -> None:
        if name.lower() in own or name.lower() == (site_name or "").lower():
            return
        known = key is not None
        key = key or name.lower()
        if key not in found and len(found) < MAX_INTEGRATION_CANDIDATES:
            found[key] = (Evidence(page.url, quote, method, item=name), known)

    def add_known(text: str, page: Page, quote: str, method: str) -> bool:
        written = _as_written(text)
        if written:
            add(written[0], page, quote, method, key=written[1])
        return written is not None

    for page in _readable(pages):
        whole_page = _is_integration_page(page)
        for image in page.images:
            if image.zone != "main" or not (whole_page or image.in_integration_section):
                continue
            name, had_suffix = _strip_suffix(image.alt)
            if not add_known(image.alt, page, image.alt, "link") and had_suffix and _plausible_name(name):
                add(name, page, image.alt, "link")
        for link in page.links:
            if link.zone == "main" and (whole_page or link.in_integration_section):
                add_known(link.text, page, link.text, "link")
        for snippet in page.snippets:
            if snippet.zone not in SPEAKING_ZONES:
                continue
            if whole_page or snippet.in_integration_section:
                cells = snippet.text.split(" | ") if snippet.method == "table" else [snippet.text]
                for cell in cells:
                    add_known(cell, page, snippet.text, snippet.method)
            if snippet.method in ("sentence", "heading"):
                trigger = find_phrase(snippet.text, INTEGRATION_TRIGGERS)
                if trigger:
                    for name in _names_after_trigger(snippet.text[trigger.end():]):
                        if not add_known(name, page, snippet.text, snippet.method):
                            add(name, page, snippet.text, snippet.method)
    if not found:
        return FieldResult()
    # Over the limit, names from the known list are kept before others: a
    # directory of thousands of apps is alphabetical, and its first 25 entries
    # say little. The names kept stay in page order.
    order = list(found)
    keep = [key for key in order if found[key][1]][:limit]
    keep += [key for key in order if not found[key][1]][:limit - len(keep)]
    chosen = [found[key][0] for key in order if key in set(keep)]
    return FieldResult([evidence.item for evidence in chosen], chosen)


# --------------------------------------------------------------------------- pricing
# A price as sites write it: "$49", "$49/month", "$1,200 a year", "€12/user/month",
# and with the currency after the amount: "42€/ month", "29 € per month", "49 EUR/month".
# "$2.5K" and "$40 million" are amounts of money, not prices.
_AMOUNT = r"\d[\d.,]*\d|\d"
_NOT_A_LARGER_NUMBER = r"(?![\d.,]*\d|\s?[kKmMbB]\b)"
_PER = (r"(?:\s*(?:/|per|a)\s*(?:(?:user|seat|member|agent|editor|workspace|account)\s*(?:/|per|a)\s*)?"
        r"(?P<period>month|mo|year|yr|annum|week)\b)?")
PRICE = re.compile(rf"(?:US\$|[$€£])\s?(?P<amount>{_AMOUNT}){_NOT_A_LARGER_NUMBER}(?:\s?(?:USD|EUR|GBP))?{_PER}",
                   re.IGNORECASE)
PRICE_CURRENCY_AFTER = re.compile(
    rf"(?<![\w.,$€£])(?P<amount>{_AMOUNT})\s?(?:[€£$]|EUR\b|USD\b|GBP\b)(?!\s?\d){_PER}", re.IGNORECASE)
# The period standing alone at the start of the element after a bare price.
_PERIOD_ALONE = re.compile(
    r"\s*(?:/|per\b|a\b)\s*(?:(?:user|seat|member|agent|editor|workspace|account)\s*(?:/|per|a)\s*)?"
    r"(?P<period>month|mo|year|yr|annum|week)\b", re.IGNORECASE)
_PERIOD_RANK = {"month": 0, "mo": 0, None: 1, "week": 2, "year": 3, "yr": 3, "annum": 3}


def _amount(text: str) -> float:
    """'1,200' -> 1200.0, '15.60' -> 15.6, '1.299,00' (continental) -> 1299.0, '129,00' -> 129.0."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{1,2}", text):
        return float(text.replace(".", "").replace(",", "."))
    return float(text.replace(",", ""))


def _is_pricing_page(page: Page) -> bool:
    return page.topic == "pricing" or bool(re.search(r"pricing|plans|price", urlsplit(page.url).path.lower()))


def _not_a_price(text: str, match: re.Match) -> bool:
    before = " ".join(re.findall(r"[\w'-]+", text[:match.start()])[-NOT_A_PRICE_WINDOW:])
    after = " ".join(re.findall(r"[\w'-]+", text[match.end():])[:NOT_A_PRICE_WINDOW])
    return has_phrase(before, NOT_A_PRICE_BEFORE) or has_phrase(after, NOT_A_PRICE_AFTER)


def _price_matches(text: str) -> list[re.Match]:
    """Every price in a text, either notation, in text order, without overlaps."""
    matches: list[re.Match] = []
    for match in sorted([*PRICE.finditer(text), *PRICE_CURRENCY_AFTER.finditer(text)], key=lambda m: m.start()):
        if not matches or match.start() >= matches[-1].end():
            matches.append(match)
    return matches


def _offers(page: Page) -> Iterator[tuple[float, str, str]]:
    """(amount, text as written, JSON quote) for every schema.org offer on a page."""
    for obj in page.json_ld:
        offers = obj.get("offers")
        for offer in offers if isinstance(offers, list) else [offers]:
            if not isinstance(offer, dict):
                continue
            for key in ("price", "lowPrice"):
                raw = offer.get(key)
                if raw is None or not re.fullmatch(r"\d+(\.\d+)?", str(raw).strip()):
                    continue
                currency = str(offer.get("priceCurrency") or "").strip()
                quote = json.dumps({k: offer[k] for k in (key, "priceCurrency") if k in offer}, ensure_ascii=False)
                yield float(raw), f"{str(raw).strip()} {currency}".strip(), quote


_CLAUSE_END = re.compile(r"\s*(?:[.,;:!?)]|$)")
_ONLY_A_PRICE = re.compile(r"\s*(?:free\W*)?" + PRICE.pattern + r"\W*$", re.IGNORECASE)


_FREE_NOUN = rf"(?:{_alternatives(FREE_NOUNS)})"
_DENIALS = (
    # "not able to offer free trials", "don't have a free plan", "no longer offers a free tier"
    re.compile(rf"(?<![\w'])(?:{_alternatives(OFFER_NEGATIONS)})(?:\s+[\w']+){{0,3}}?\s+(?:{_alternatives(OFFER_VERBS)})"
               rf"(?:\s+(?:a|any|the))?\s+{_FREE_NOUN}(?![\w'])", re.IGNORECASE),
    # "There is no free plan."  (but not "No free trial limits.")
    re.compile(rf"(?<![\w'])no\s+{_FREE_NOUN}\s*(?:[.,;:!?)]|$)", re.IGNORECASE),
    # "Free trials are not available."
    re.compile(rf"(?<![\w']){_FREE_NOUN}\s+(?:is|are)\s+(?:{_alternatives(NOT_AVAILABLE)})(?![\w'])", re.IGNORECASE),
)


def _denies_free_tier(text: str) -> bool:
    """The sentence says the product has no free plan or trial (see OFFER_VERBS in vocab.py)."""
    text = normalise_quotes(text)
    return any(pattern.search(text) for pattern in _DENIALS)


def _zero_is_a_free_plan(snippet: Snippet) -> bool:
    """A price of zero is a free plan in a pricing table row or standing alone
    ("$0", "$0/month"), unless the row is about a fee ("Setup fee | $0")."""
    if has_phrase(snippet.text, NOT_A_FREE_PLAN):
        return False
    return snippet.method == "table" or bool(_ONLY_A_PRICE.match(snippet.text))


def extract_pricing(pages: list[Page]) -> FieldResult:
    prices: list[tuple[int, float, int, str, Evidence]] = []     # period rank, amount, order, text, evidence
    free: Evidence | None = None
    no_free: Evidence | None = None
    ordered = sorted(_readable(pages), key=lambda page: not _is_pricing_page(page))
    for page in ordered:
        whole_page = _is_pricing_page(page)
        spoken = _spoken(page, ("heading", "sentence", "link", "table"))
        for index, snippet in enumerate(spoken):
            text = snippet.text
            # a pricing page, or a pricing section of another page (a one-page site)
            priced = whole_page or snippet.in_pricing_section
            if _denies_free_tier(text):
                no_free = no_free or Evidence(page.url, text, snippet.method, item="free_tier")
            elif has_phrase(text, FREE_TIER_PHRASES):
                free = free or Evidence(page.url, text, snippet.method, item="free_tier")
            elif priced and snippet.method in ("heading", "table") and \
                    text.split(" | ")[0].strip().lower() in ("free", "free plan"):
                free = free or Evidence(page.url, text, snippet.method, item="free_tier")
            for match in _price_matches(text):
                amount = _amount(match.group("amount"))
                if _not_a_price(text, match):
                    continue
                if amount == 0:
                    if priced and _zero_is_a_free_plan(snippet):
                        free = free or Evidence(page.url, text, snippet.method, item="free_tier")
                    continue
                if not priced and not has_phrase(text, PRICE_CUES):
                    continue
                period = (match.group("period") or "").lower() or None
                written, quote = " ".join(match.group(0).split()), text
                if period is None and not text[match.end():].strip() and index + 1 < len(spoken):
                    # "$149" in one element and "per month" in the next
                    alone = _PERIOD_ALONE.match(spoken[index + 1].text)
                    if alone and len(spoken[index + 1].text) <= 40:
                        period = alone.group("period").lower()
                        written = f"{written} {' '.join(alone.group(0).split())}"
                        quote = f"{text} {spoken[index + 1].text}"
                prices.append((_PERIOD_RANK[period], amount, len(prices), written,
                               Evidence(page.url, quote, snippet.method, item="starting_price")))

    evidence: list[Evidence] = []
    starting: str = UNKNOWN
    if prices:
        _, _, _, starting, proof = min(prices, key=lambda entry: entry[:3])
        evidence.append(proof)
    offers = [(amount, written, quote, page) for page in pages for amount, written, quote in _offers(page)]
    if starting == UNKNOWN and any(amount > 0 for amount, *_ in offers):
        amount, starting, quote, page = min((o for o in offers if o[0] > 0), key=lambda o: o[0])
        evidence.append(Evidence(page.url, quote, "json-ld", item="starting_price"))
    if free is None and no_free is None:
        zero = next((o for o in offers if o[0] == 0), None)
        if zero:
            free = Evidence(zero[3].url, zero[2], "json-ld", item="free_tier")

    free_tier: bool | str = UNKNOWN
    if free:
        free_tier = True
        evidence.insert(0, free)
    elif no_free:
        free_tier = False
        evidence.insert(0, no_free)
    if free_tier == UNKNOWN and starting == UNKNOWN:
        return FieldResult()
    return FieldResult({"free_tier": free_tier, "starting_price": starting}, evidence)


# --------------------------------------------------------------------------- hq_location
def _place(city: str | None, country: str | None) -> dict | None:
    if not city and not country:
        return None
    return {"city": city or UNKNOWN, "country": country or UNKNOWN}


def _json_ld_place(address) -> tuple[str | None, str | None]:
    if isinstance(address, list):
        address = address[0] if address else None
    if isinstance(address, str):
        return parse_place(address)
    if not isinstance(address, dict):
        return None, None
    city = address.get("addressLocality")
    city = " ".join(city.split()) if isinstance(city, str) and city.strip() else None
    raw_country = address.get("addressCountry")
    if isinstance(raw_country, dict):
        raw_country = raw_country.get("name") or raw_country.get("identifier")
    country = country_name(raw_country, allow_code=True) if isinstance(raw_country, str) else None
    region = address.get("addressRegion")
    postcode = address.get("postalCode")
    if country is None and isinstance(region, str):
        # a region code alone does not state the country; a US state with a ZIP code does
        zip_code = f" {postcode.strip()}" if isinstance(postcode, str) else ""
        if states_the_united_states(region + zip_code):
            country = "United States"
    return city, country


def _place_after_cue(rest: str) -> tuple[str | None, str | None]:
    rest = re.split(r"\s+(?:and|with|since|but|where|while|who|which)\s+|[.;:!?(]\s|[.;!?]$|\s[-–—]\s", rest.strip(),
                    maxsplit=1)[0].strip(" .,")
    if not rest or rest.lower() in NOT_A_CITY:
        return None, None
    city, country = parse_place(rest)
    if country or city:
        return city, country
    words = rest.split()
    if "," not in rest and 0 < len(words) <= 3 and all(word[0].isupper() for word in words) \
            and not any(ch.isdigit() for ch in rest):
        return rest, None
    return None, None


def extract_hq(pages: list[Page]) -> FieldResult:
    for page in pages:                                  # head data: also from JavaScript shells
        typed = sorted(page.json_ld, key=lambda obj: not ({"Organization", "Corporation", "LocalBusiness"} & _types(obj)))
        for obj in typed:
            address = obj.get("address")
            if address is None:
                continue
            place = _place(*_json_ld_place(address))
            if place:
                quote = json.dumps({"address": address}, ensure_ascii=False)
                return FieldResult(place, [Evidence(page.url, quote, "json-ld")])
    readable = _readable(pages)
    for page in readable:
        for address in page.addresses:
            city, country = parse_place(address)
            if city or country:
                return FieldResult(_place(city, country), [Evidence(page.url, address, "sentence")])
    company_zones = (*SPEAKING_ZONES, "footer")      # a footer is where a company states its address
    for page in readable:
        candidates = [Snippet(page.meta["description"], "meta", "head")] if page.meta.get("description") else []
        candidates += [s for s in page.snippets if s.method in ("sentence", "heading") and s.zone in company_zones]
        for snippet in candidates:
            cue = find_phrase(snippet.text, HQ_CUES)
            if cue is None or has_phrase(snippet.text[:cue.start()], THIRD_PARTIES):
                continue                                   # "our customer X, based in ..." is not us
            place = _place(*_place_after_cue(snippet.text[cue.end():]))
            if place:
                return FieldResult(place, [Evidence(page.url, snippet.text, snippet.method)])
    for page in readable:
        for snippet in page.snippets:
            if snippet.method != "sentence" or snippet.zone not in company_zones:
                continue
            if not (snippet.zone == "footer" or page.topic in ("about", "contact")):
                continue
            if not any(ch.isdigit() for ch in snippet.text) or "," not in snippet.text:
                continue
            city, country = parse_place(snippet.text)
            if city and country:
                return FieldResult(_place(city, country), [Evidence(page.url, snippet.text, "sentence")])
    return FieldResult()


# --------------------------------------------------------------------------- whole site
def extract_fields(pages: list[Page], site_name: str | None, config: Config,
                   site: str | None = None) -> dict[str, FieldResult]:
    """Run every extractor; one logged span per field with the methods used."""
    extractors = {
        "one_liner": lambda: extract_one_liner(pages),
        "categories": lambda: extract_vocab(pages, "categories"),
        "target_user": lambda: extract_vocab(pages, "target_user"),
        "tasks": lambda: extract_vocab(pages, "tasks"),
        "can_execute": lambda: extract_can_execute(pages, site),
        "multi_agent": lambda: extract_multi_agent(pages),
        "integrations": lambda: extract_integrations(pages, site_name, config.max_integrations),
        "pricing": lambda: extract_pricing(pages),
        "hq_location": lambda: extract_hq(pages),
    }
    fields = unknown_fields()
    for name in FIELDS:
        with obs.span("extract", site=site, field=name) as span:
            fields[name] = extractors[name]() if pages else FieldResult()
            if fields[name].known:
                span.context["methods"] = sorted({e.method for e in fields[name].evidence})
            else:
                span.skip("not_stated")
    return fields
