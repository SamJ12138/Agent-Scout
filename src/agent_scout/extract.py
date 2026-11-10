"""Rule-based extraction of every schema field from the pages of one site.

Each function returns a FieldResult: a value (or "unknown") plus the evidence
it rests on (page URL, verbatim quote, method). Nothing is inferred beyond
what a quote states; a field no page states stays "unknown".

From a page flagged ``needs_rendering`` only head data is used (meta tags for
the one-liner, JSON-LD for address and offers). Keyword tables are never run
on such a page: its visible text is a loading shell.
"""

from __future__ import annotations

import json
import re
from typing import Iterator
from urllib.parse import urlsplit

from . import obs
from .config import Config
from .geo import country_name, parse_place, us_state
from .model import FIELDS, UNKNOWN, Evidence, FieldResult, unknown_fields
from .page import Page, Snippet, split_sentences
from .textmatch import find_all, find_phrase, has_phrase
from .vocab import (AGENT_SUBJECTS, ASSIST_WORDS, AUTONOMY_MARKERS, CATEGORIES, DRAFT_ONLY_PHRASES,
                    EXECUTE_OBJECTS, EXECUTE_VERBS, FREE_TIER_PHRASES, HQ_CUES, INTEGRATION_TRIGGERS,
                    KNOWN_INTEGRATIONS, LOGO_SUFFIXES, MULTI_AGENT_PHRASES, NO_FREE_TIER_PHRASES,
                    NOT_A_CITY, NOT_A_PRICE_AFTER, NOT_A_PRICE_BEFORE, NOT_A_PRODUCT, PRICE_CUES,
                    STRONG_HIT, TARGET_USERS, TASKS, THRESHOLDS, WEAK_HIT)

VOCAB_TABLES = {"categories": CATEGORIES, "target_user": TARGET_USERS, "tasks": TASKS}
DESCRIBING_TYPES = {"SoftwareApplication", "WebApplication", "Product", "Organization", "Corporation",
                    "WebSite", "Service"}
MAX_ONE_LINER_CHARS = 300


def _readable(pages: list[Page]) -> list[Page]:
    return [page for page in pages if not page.needs_rendering]


def _statements(pages: list[Page]) -> Iterator[tuple[Page, Snippet]]:
    """What the site says about the product: head descriptions, headings and
    sentences of the main content. Navigation, footers, link-only text, table
    rows and anything presented as a list of integrations are left out, and a
    text repeated across pages is yielded once."""
    seen: set[str] = set()
    for page in _readable(pages):
        if page.topic == "integrations":
            continue
        head = [page.meta.get("description"), page.meta.get("og:description"), page.title]
        candidates = [Snippet(text, "meta", "head") for text in head if text]
        candidates += [s for s in page.snippets
                       if s.method in ("heading", "sentence") and s.zone not in ("nav", "footer")
                       and not s.in_integration_section]
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
        kinds = obj.get("@type")
        kinds = set(kinds if isinstance(kinds, list) else [kinds])
        if kinds & DESCRIBING_TYPES and isinstance(obj.get("description"), str) and obj["description"].strip():
            text = _trim(" ".join(obj["description"].split()))
            return FieldResult(text, [Evidence(home.url, text, "json-ld")])
    if home.needs_rendering:
        return FieldResult()
    body = [s for s in home.snippets if s.zone not in ("nav", "footer")]
    for index, snippet in enumerate(body):
        if snippet.method != "heading":
            continue
        following = next((s for s in body[index + 1:] if s.method in ("sentence", "heading")), None)
        if following is None or following.method != "sentence":
            return FieldResult()
        joiner = " " if snippet.text[-1] in ".!?:" else ": "
        return FieldResult(_trim(f"{snippet.text}{joiner}{following.text}"),
                           [Evidence(home.url, snippet.text, "heading"),
                            Evidence(home.url, following.text, "sentence")])
    return FieldResult()


# --------------------------------------------------------------------------- vocabulary fields
def extract_vocab(pages: list[Page], field: str) -> FieldResult:
    """categories / target_user / tasks: labels whose phrases the site uses."""
    table = VOCAB_TABLES[field]
    scores: dict[str, int] = {}
    evidence: dict[str, tuple[int, Evidence]] = {}
    for page, snippet in _statements(pages):
        weight = STRONG_HIT if snippet.method in ("meta", "heading") else WEAK_HIT
        for label, phrases in table.items():
            if not has_phrase(snippet.text, phrases):
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
    objects = find_all(text, EXECUTE_OBJECTS)
    autonomous = has_phrase(text, AUTONOMY_MARKERS)
    for verb in find_all(text, EXECUTE_VERBS):
        if not any(obj.end() <= verb.start() or obj.start() >= verb.end() for obj in objects):
            continue                                   # the verb needs an object of its own
        before = text[:verb.start()]
        if has_phrase(before, ASSIST_WORDS):
            continue                                   # "helps you launch", "drafts ... to post"
        if autonomous or has_phrase(before, AGENT_SUBJECTS):
            return True
    return False


def extract_can_execute(pages: list[Page], site: str | None = None) -> FieldResult:
    acts: Evidence | None = None
    drafts: Evidence | None = None
    for page, snippet in _statements(pages):
        if has_phrase(snippet.text, DRAFT_ONLY_PHRASES):
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
        if has_phrase(snippet.text, MULTI_AGENT_PHRASES):
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
    """'Instagram, LinkedIn and Slack to keep ...' -> the capitalised names."""
    rest = re.split(r"[.;:!?(]\s|[.;:!?]$", rest, maxsplit=1)[0]
    names = []
    for token in re.split(r",|\band\b|&|\bor\b|\bplus\b", rest):
        words = token.strip().strip(".").split()
        run: list[str] = []
        for word in words:
            if (word[0].isupper() or word[0].isdigit()) and len(run) < 3:
                run.append(word.rstrip(".,"))
            else:
                break
        while run:
            candidate = " ".join(run)
            canonical = _KNOWN_LOOKUP.get(candidate.lower())
            if canonical:
                names.append(canonical)
                break
            if len(run) == len(words[:len(run)]) and _plausible_name(candidate) and len(run) <= 3:
                names.append(candidate)
                break
            run.pop()
        if not run and words and words[0][0].islower():
            continue
    return names


def _is_integration_page(page: Page) -> bool:
    return page.topic == "integrations" or bool(re.search(r"integrat|connector", urlsplit(page.url).path.lower()))


def extract_integrations(pages: list[Page], site_name: str | None, limit: int) -> FieldResult:
    found: dict[str, Evidence] = {}
    own = {word.lower() for word in re.findall(r"\w+", site_name or "")}

    def add(name: str, page: Page, quote: str, method: str) -> None:
        if name.lower() in own or name.lower() == (site_name or "").lower():
            return
        key = name.lower()
        if key not in found and len(found) < limit:
            found[key] = Evidence(page.url, quote, method, item=name)

    for page in _readable(pages):
        whole_page = _is_integration_page(page)
        for image in page.images:
            if image.zone != "main" or not (whole_page or image.in_integration_section):
                continue
            name, had_suffix = _strip_suffix(image.alt)
            canonical = known_integration(image.alt)
            if canonical:
                add(canonical, page, image.alt, "link")
            elif had_suffix and _plausible_name(name):
                add(name, page, image.alt, "link")
        for link in page.links:
            if link.zone == "main" and (whole_page or link.in_integration_section):
                canonical = known_integration(link.text)
                if canonical:
                    add(canonical, page, link.text, "link")
        for snippet in page.snippets:
            if snippet.zone in ("nav", "footer"):
                continue
            if whole_page or snippet.in_integration_section:
                cells = snippet.text.split(" | ") if snippet.method == "table" else [snippet.text]
                for cell in cells:
                    canonical = known_integration(cell)
                    if canonical:
                        add(canonical, page, snippet.text, snippet.method)
            if snippet.method in ("sentence", "heading"):
                trigger = find_phrase(snippet.text, INTEGRATION_TRIGGERS)
                if trigger:
                    for name in _names_after_trigger(snippet.text[trigger.end():]):
                        add(name, page, snippet.text, snippet.method)
    if not found:
        return FieldResult()
    return FieldResult([e.item for e in found.values()], list(found.values()))


# --------------------------------------------------------------------------- pricing
PRICE = re.compile(
    r"(?:US\$|[$€£])\s?(?P<amount>\d[\d,]*(?:\.\d+)?)(?!\s?(?:[kKmMbB]\b|\d))"
    r"(?:\s?(?:USD|EUR|GBP))?"
    r"(?:\s*(?:/|per|a)\s*(?:(?:user|seat|member|agent|editor|workspace|account)\s*(?:/|per|a)\s*)?"
    r"(?P<period>month|mo|year|yr|annum|week)\b)?",
    re.IGNORECASE)
_PERIOD_RANK = {"month": 0, "mo": 0, None: 1, "week": 2, "year": 3, "yr": 3, "annum": 3}


def _is_pricing_page(page: Page) -> bool:
    return page.topic == "pricing" or bool(re.search(r"pricing|plans|price", urlsplit(page.url).path.lower()))


def _not_a_price(text: str, match: re.Match) -> bool:
    before = " ".join(re.findall(r"[\w']+", text[:match.start()])[-3:])
    after = " ".join(re.findall(r"[\w']+", text[match.end():])[:2])
    return has_phrase(before, NOT_A_PRICE_BEFORE) or has_phrase(after, NOT_A_PRICE_AFTER)


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


def extract_pricing(pages: list[Page]) -> FieldResult:
    prices: list[tuple[int, float, int, str, Evidence]] = []     # period rank, amount, order, text, evidence
    free: Evidence | None = None
    no_free: Evidence | None = None
    ordered = sorted(_readable(pages), key=lambda page: not _is_pricing_page(page))
    for page in ordered:
        pricing_page = _is_pricing_page(page)
        for snippet in page.snippets:
            text = snippet.text
            if has_phrase(text, NO_FREE_TIER_PHRASES):
                no_free = no_free or Evidence(page.url, text, snippet.method, item="free_tier")
            elif has_phrase(text, FREE_TIER_PHRASES):
                free = free or Evidence(page.url, text, snippet.method, item="free_tier")
            elif pricing_page and snippet.method in ("heading", "table") and \
                    text.split(" | ")[0].strip().lower() in ("free", "free plan"):
                free = free or Evidence(page.url, text, snippet.method, item="free_tier")
            for match in PRICE.finditer(text):
                amount = float(match.group("amount").replace(",", ""))
                if _not_a_price(text, match):
                    continue
                if amount == 0:
                    if pricing_page:
                        free = free or Evidence(page.url, text, snippet.method, item="free_tier")
                    continue
                if not pricing_page and not has_phrase(text, PRICE_CUES):
                    continue
                period = (match.group("period") or "").lower() or None
                written = " ".join(match.group(0).split())
                prices.append((_PERIOD_RANK[period], amount, len(prices), written,
                               Evidence(page.url, text, snippet.method, item="starting_price")))

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
    if country is None and isinstance(region, str) and us_state(region):
        country = "United States"
    return city, country


def _place_after_cue(rest: str) -> tuple[str | None, str | None]:
    rest = re.split(r"\s+(?:and|with|since|but|where|while|who|which)\s+|[.;:!?(]\s|[.;!?]$|\s[-–—]\s", rest.strip(),
                    maxsplit=1)[0].strip(" .,")
    if not rest or rest.lower() in NOT_A_CITY:
        return None, None
    city, country = parse_place(rest)
    if country:
        return city, country
    words = rest.split()
    if "," not in rest and 0 < len(words) <= 3 and all(word[0].isupper() for word in words) \
            and not any(ch.isdigit() for ch in rest):
        return rest, None
    return None, None


def extract_hq(pages: list[Page]) -> FieldResult:
    for page in pages:                                  # head data: also from JavaScript shells
        typed = sorted(page.json_ld, key=lambda obj: not (
            {"Organization", "Corporation", "LocalBusiness"} & set(
                obj.get("@type") if isinstance(obj.get("@type"), list) else [obj.get("@type")])))
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
            if country:
                return FieldResult(_place(city, country), [Evidence(page.url, address, "sentence")])
    for page in readable:
        candidates = [Snippet(page.meta["description"], "meta", "head")] if page.meta.get("description") else []
        candidates += [s for s in page.snippets if s.method in ("sentence", "heading")]
        for snippet in candidates:
            cue = find_phrase(snippet.text, HQ_CUES)
            if cue:
                place = _place(*_place_after_cue(snippet.text[cue.end():]))
                if place:
                    return FieldResult(place, [Evidence(page.url, snippet.text, snippet.method)])
    for page in readable:
        for snippet in page.snippets:
            if snippet.method != "sentence" or not (snippet.zone == "footer" or page.topic in ("about", "contact")):
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
