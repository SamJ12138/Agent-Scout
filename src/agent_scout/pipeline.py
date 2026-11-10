"""Run the whole pipeline for a list of sites and build the results document.

results.json, schema version 1.0
--------------------------------
{
  "schema_version": "1.0",
  "tool": {"name": "agent-scout", "version": "..."},
  "run_id": "...",                      # also in the name of the run log
  "started_at": "...Z", "finished_at": "...Z",
  "settings": {page_budget, delay_seconds, max_crawl_delay_seconds,
               timeout_seconds, user_agent, llm: {enabled, provider, model}},
  "sites": [{
    "slug", "name", "url",              # as given in the sites file
    "final_url",                        # homepage URL after redirects, or null
    "status",                           # ok | partial | blocked | unreachable | robots_disallowed
    "status_detail",                    # one sentence saying why
    "needs_rendering",                  # true when a page was a JavaScript shell
    "robots": {state, http_status, crawl_delay},
    "pages": [{url, final_url, topic, outcome, http_status, error_type,
               bytes, encoding, charset}],
    "llm": null | {status, added, dropped, error_type},
    "fields": {
      "<field>": {
        "value": ... | "unknown",
        "evidence": [{"item", "url", "quote", "method"}]
      }
    }
  }]
}

Field values: one_liner is a string; categories, target_user, tasks and
integrations are lists; can_execute is true/false; multi_agent is true;
pricing is {"free_tier": true|false|"unknown", "starting_price": "..."|"unknown"};
hq_location is {"city": ...|"unknown", "country": ...|"unknown"}. Any field
may be the string "unknown", which means the site does not state it; an
unknown field has no evidence. ``item`` names the list entry or sub-value an
evidence quote supports (null when it supports the whole value). ``method`` is
meta | json-ld | heading | sentence | link | table | llm. For ``table`` the
quote is the cells of one row joined by " | "; for ``json-ld`` it is the
relevant JSON fragment.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from . import USER_AGENT, __version__, obs
from .config import Config
from .crawl import PageRecord, SiteCrawl, crawl_site
from .extract import extract_fields
from .fetch import Fetcher
from .inputs import SiteInput
from .model import FIELDS, SCHEMA_VERSION, FieldResult, unknown_fields

NO_DATA_STATUSES = ("blocked", "unreachable", "robots_disallowed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def display_name(site: SiteInput, crawl: SiteCrawl) -> str:
    """The name given in the sites file, else the site's own name, else its host."""
    if site.name:
        return site.name
    if crawl.pages:
        home = crawl.pages[0]
        if home.meta.get("og:site_name"):
            return home.meta["og:site_name"]
        first = re.split(r"\s+[|–—:-]\s+", home.title)[0].strip() if home.title else ""
        if first:
            return first
    return urlsplit(site.url).hostname or site.slug


class Progress:
    """Console output of a run. ``write`` receives one line at a time."""

    def __init__(self, write: Callable[[str], None] | None):
        self._write = write

    def line(self, text: str = "") -> None:
        if self._write:
            self._write(text)

    def robots(self, policy) -> None:
        status = f"HTTP {policy.http_status}" if policy.http_status else "no answer"
        if policy.state == "ok":
            delay = f", Crawl-delay {policy.crawl_delay:g}s" if policy.crawl_delay else ""
            count = len(policy.rules)
            note = f"{count} rule{' applies' if count == 1 else 's apply'} to agent-scout{delay}"
        elif policy.state == "missing":
            note = "no restrictions"
        else:
            note = "the site is off limits for this run"
        self.line(f"      robots.txt  {status}: {note}")

    def page(self, record: PageRecord) -> None:
        path = urlsplit(record.final_url)
        shown = (path.path or "/") + (f"?{path.query}" if path.query else "")
        if record.outcome == "robots_disallowed":
            if record.error_type == "robots_disallowed":
                self.line(f"      skip  {shown:<28} disallowed by robots.txt")
            return
        status = str(record.http_status) if record.http_status else "---"
        size = f"{record.bytes / 1000:.1f} kB" if record.bytes else ""
        note = {"fetched": record.encoding or "", "needs_rendering": "JavaScript shell, not interpreted",
                "blocked": "blocked", "error": record.error_type or "error"}[record.outcome]
        self.line(f"      {status:<5} {shown:<28} {size:>8}  {note}")


def profile_site(site: SiteInput, fetcher: Fetcher, config: Config, progress: Progress) -> dict[str, Any]:
    with obs.span("run", site=site.slug, url=site.url) as span:
        seen_robots = []

        def on_record(record: PageRecord) -> None:
            if not seen_robots:
                seen_robots.append(True)
                progress.robots(fetcher.robots_for(record.final_url, site=site.slug))
            progress.page(record)

        crawl = crawl_site(site, fetcher, config, on_record=on_record)
        name = display_name(site, crawl)
        fields: dict[str, FieldResult]
        if crawl.status in NO_DATA_STATUSES:
            fields = unknown_fields()
            for field_name in FIELDS:
                obs.emit("extract", "skip", site=site.slug, error_type=f"site_{crawl.status}", field=field_name)
        else:
            fields = extract_fields(crawl.pages, name, config, site=site.slug)
        span.context.update(status=crawl.status, known=sum(1 for f in fields.values() if f.known))
        if crawl.status in NO_DATA_STATUSES:
            span.skip(f"site_{crawl.status}")
    return {
        "slug": site.slug,
        "name": name,
        "url": site.url,
        "final_url": crawl.final_url,
        "status": crawl.status,
        "status_detail": crawl.detail,
        "needs_rendering": crawl.needs_rendering,
        "robots": crawl.robots,
        "pages": [asdict(record) for record in crawl.records],
        "llm": None,
        "fields": {field_name: fields[field_name].as_dict() for field_name in FIELDS},
        "_pages": crawl.pages,     # parsed pages for the optional LLM pass; removed before writing
    }


def run_sites(sites: list[SiteInput], config: Config, run_id: str, *,
              fetcher: Fetcher | None = None, write: Callable[[str], None] | None = None,
              after_site: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Profile every site, one after another, and return the results document."""
    progress = Progress(write)
    fetcher = fetcher or Fetcher(config)
    started = _now()
    progress.line(f"agent-scout {__version__}   run {run_id}   {len(sites)} site{'s' if len(sites) != 1 else ''}"
                  f"   delay {config.delay_seconds:g}s   budget {config.page_budget} pages per site")
    results_sites = []
    for index, site in enumerate(sites, 1):
        progress.line("")
        progress.line(f"[{index}/{len(sites)}] {site.name or site.slug}   {site.url}")
        result = profile_site(site, fetcher, config, progress)
        if after_site:
            after_site(result)
        result.pop("_pages", None)
        known = [name for name in FIELDS if result["fields"][name]["value"] != "unknown"]
        unknown = [name for name in FIELDS if name not in known]
        progress.line(f"      {result['status']}: {result['status_detail']}")
        if result["status"] in NO_DATA_STATUSES:
            progress.line("      nothing is reported about this site: every field is unknown")
        else:
            progress.line(f"      {len(known)} of {len(FIELDS)} fields stated"
                          + (f"; unknown: {', '.join(unknown)}" if unknown else ""))
        results_sites.append(result)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "agent-scout", "version": __version__},
        "run_id": run_id,
        "started_at": started,
        "finished_at": _now(),
        "settings": {
            "page_budget": config.page_budget,
            "delay_seconds": config.delay_seconds,
            "max_crawl_delay_seconds": config.max_crawl_delay_seconds,
            "timeout_seconds": config.timeout_seconds,
            "user_agent": USER_AGENT,
            "llm": {"enabled": config.llm.enabled, "provider": config.llm.provider if config.llm.enabled else None,
                    "model": config.llm.model if config.llm.enabled else None},
        },
        "sites": results_sites,
    }
