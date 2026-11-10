"""Read one site: the homepage, then a few same-site pages chosen from its links.

Site status
    ok                 every page that was requested was read
    partial            the homepage was read, but a page failed or a page is a
                       JavaScript shell (needs_rendering)
    blocked            a 401 / 403 / 429 or a challenge page was met, on any
                       page: the crawl stops and nothing is reported
    unreachable        the start URL could not be fetched (network error,
                       timeout, 4xx/5xx other than a block, undecodable body)
    robots_disallowed  robots.txt forbids the start URL, could not be read
                       (5xx), or asks for a longer Crawl-delay than allowed

Pages disallowed by robots.txt are recorded and skipped; they do not count
against the page budget and do not make a site "partial".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import obs
from .config import Config
from .fetch import Fetcher, FetchResult
from .inputs import SiteInput
from .links import page_identity, same_site, select_links
from .page import Page, parse_page

SITE_STATUSES = ("ok", "partial", "blocked", "unreachable", "robots_disallowed")


@dataclass
class PageRecord:
    url: str                       # URL requested
    final_url: str                 # URL that answered
    topic: str                     # home | product | integrations | pricing | about | contact | customers
    outcome: str                   # fetched | needs_rendering | robots_disallowed | blocked | error
    http_status: int | None = None
    error_type: str | None = None
    bytes: int = 0
    encoding: str | None = None
    charset: str | None = None


@dataclass
class SiteCrawl:
    site: SiteInput
    status: str = "unreachable"
    detail: str = ""
    final_url: str | None = None
    pages: list[Page] = field(default_factory=list)       # parsed pages, homepage first
    records: list[PageRecord] = field(default_factory=list)
    needs_rendering: bool = False
    robots: dict = field(default_factory=dict)


def _record(result: FetchResult, topic: str, outcome: str) -> PageRecord:
    return PageRecord(url=result.url, final_url=result.final_url, topic=topic, outcome=outcome,
                      http_status=result.status, error_type=result.error_type, bytes=result.wire_bytes,
                      encoding=result.content_encoding or ("identity" if outcome in ("fetched", "needs_rendering") else None),
                      charset=result.charset)


def _block_detail(result: FetchResult) -> str:
    what = "a challenge page" if result.error_type == "challenge_page" else f"HTTP {result.status}"
    return f"{what} at {result.final_url}; the tool does not try to get around it"


def _robots_detail(result: FetchResult) -> str:
    if result.error_type == "crawl_delay_too_long":
        return "robots.txt asks for a longer Crawl-delay than max_crawl_delay_seconds"
    if result.error_type == "robots_unreachable":
        return f"robots.txt returned HTTP {result.status}; treated as disallow for this run (RFC 9309)"
    return f"robots.txt disallows {result.final_url}"


def crawl_site(site: SiteInput, fetcher: Fetcher, config: Config,
               on_record: Callable[[PageRecord], None] | None = None) -> SiteCrawl:
    """``on_record`` is called for every page record as it is made (progress output)."""
    crawl = SiteCrawl(site=site)
    slug = site.slug

    def note(record: PageRecord) -> None:
        crawl.records.append(record)
        if on_record:
            on_record(record)

    home = fetcher.get(site.url, site=slug)
    policy = fetcher.robots_for(home.final_url, site=slug)
    crawl.robots = {"state": policy.state, "http_status": policy.http_status, "crawl_delay": policy.crawl_delay}
    if home.outcome == "robots_disallowed":
        if home.error_type == "robots_unreachable" and home.status is None:
            crawl.status, crawl.detail = "unreachable", "could not connect (the robots.txt request failed)"
        else:
            crawl.status, crawl.detail = "robots_disallowed", _robots_detail(home)
        note(_record(home, "home", "robots_disallowed"))
        return crawl
    if home.outcome == "blocked":
        crawl.status, crawl.detail = "blocked", _block_detail(home)
        note(_record(home, "home", "blocked"))
        return crawl
    if home.outcome != "ok":
        reason = f"HTTP {home.status}" if home.error_type == f"http_{home.status}" else home.error_type
        crawl.status, crawl.detail = "unreachable", f"the start URL could not be read ({reason})"
        note(_record(home, "home", "error"))
        return crawl

    crawl.final_url = home.final_url
    failures: list[str] = []

    def add_page(result: FetchResult, topic: str) -> Page:
        with obs.span("parse", site=slug, url=result.final_url) as span:
            page = parse_page(result.final_url, result.text or "", config)
            page.topic = topic
            span.context.update(visible_chars=page.visible_chars, needs_rendering=page.needs_rendering)
        crawl.pages.append(page)
        note(_record(result, topic, "needs_rendering" if page.needs_rendering else "fetched"))
        if page.needs_rendering:
            crawl.needs_rendering = True
            obs.emit("parse", "skip", site=slug, error_type="needs_rendering", url=result.final_url)
        return page

    home_page = add_page(home, "home")
    fetched = {page_identity(home.final_url)}
    requested = 1
    for candidate in select_links(home_page, home.final_url):
        if requested >= config.page_budget:
            break
        if page_identity(candidate.url) in fetched:
            continue
        result = fetcher.get(candidate.url, site=slug)
        if result.outcome == "robots_disallowed":
            note(_record(result, candidate.topic, "robots_disallowed"))
            continue
        requested += 1
        if result.outcome == "blocked":
            note(_record(result, candidate.topic, "blocked"))
            crawl.status, crawl.detail = "blocked", _block_detail(result)
            crawl.pages = []
            crawl.needs_rendering = False
            return crawl
        if result.outcome == "ok" and not same_site(result.final_url, home.final_url):
            obs.emit("fetch", "skip", site=slug, error_type="offsite_redirect", url=result.final_url)
            result.outcome, result.error_type = "error", "offsite_redirect"
        if result.outcome != "ok":
            note(_record(result, candidate.topic, "error"))
            failures.append(result.error_type or "error")
            continue
        if page_identity(result.final_url) in fetched:
            obs.emit("fetch", "skip", site=slug, error_type="duplicate_page", url=result.final_url)
            continue
        fetched.add(page_identity(result.final_url))
        add_page(result, candidate.topic)

    read = sum(1 for record in crawl.records if record.outcome == "fetched")
    notes = []
    if crawl.needs_rendering:
        shells = sum(1 for record in crawl.records if record.outcome == "needs_rendering")
        notes.append("1 page needs JavaScript rendering and was not interpreted" if shells == 1 else
                     f"{shells} pages need JavaScript rendering and were not interpreted")
    if failures:
        notes.append(f"{len(failures)} page{'s' if len(failures) != 1 else ''} failed ({', '.join(sorted(set(failures)))})")
    crawl.status = "partial" if notes else "ok"
    crawl.detail = "; ".join([f"{read} page{'s' if read != 1 else ''} read", *notes])
    return crawl
