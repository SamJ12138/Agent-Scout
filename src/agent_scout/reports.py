"""Write the outputs of a run: results.json, results.csv, report.md, report.html.

One rule holds in every format: a field the site does not state is written
as the word "unknown". It is never rendered as "no", "none", "false" or an
empty cell, because the tool did not learn that the answer is no. A stated
negative (the site says it only drafts; the site says it has no free plan) is
written as a statement.
"""

from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from . import obs
from .model import FIELD_LABELS, FIELDS, LIST_FIELDS, UNKNOWN

REACHABLE = ("ok", "partial")
STATUS_LABELS = {
    "ok": "read",
    "partial": "partly read",
    "blocked": "blocked",
    "unreachable": "unreachable",
    "robots_disallowed": "ruled out by robots.txt",
}
METHOD_LABELS = {
    "meta": "meta tag", "json-ld": "JSON-LD", "heading": "heading", "sentence": "sentence",
    "link": "link or logo text", "table": "table row", "llm": "LLM, quote verified",
}


ITEM_LABELS = {"free_tier": "free plan or trial", "starting_price": "starting price"}
TABLE_FIELDS = ("categories", "target_user", "can_execute", "multi_agent", "pricing", "hq_location", "integrations")


# --------------------------------------------------------------------------- shared formatting
def display(field: str, value: Any) -> str:
    """One field value as plain text."""
    if value == UNKNOWN:
        return UNKNOWN
    if field in LIST_FIELDS:
        return ", ".join(str(item) for item in value)
    if field == "can_execute":
        return "yes" if value is True else "drafts only"
    if field == "multi_agent":
        return "yes"
    if field == "pricing":
        free = value.get("free_tier", UNKNOWN)
        price = value.get("starting_price", UNKNOWN)
        free_text = {True: "free plan or trial", False: "states it has no free plan or trial"}.get(
            free, "free plan or trial unknown")
        return f"{free_text}; " + (f"from {price}" if price != UNKNOWN else "price unknown")
    if field == "hq_location":
        city, country = value.get("city", UNKNOWN), value.get("country", UNKNOWN)
        if city != UNKNOWN and country != UNKNOWN:
            return f"{city}, {country}"
        return f"{city} (country unknown)" if city != UNKNOWN else f"{country} (city unknown)"
    return str(value)


def _value(site: dict, field: str) -> Any:
    return site["fields"][field]["value"]


def _country(site: dict) -> str:
    value = _value(site, "hq_location")
    country = value.get("country", UNKNOWN) if isinstance(value, dict) else UNKNOWN
    return "" if country == UNKNOWN else country


def _categories(site: dict) -> list[str]:
    value = _value(site, "categories")
    return list(value) if isinstance(value, list) else []


def _pages_read(site: dict) -> int:
    return sum(1 for page in site.get("pages", []) if page.get("outcome") == "fetched")


def coverage(results: dict) -> tuple[int, dict[str, int]]:
    """(number of reachable sites, field -> how many of them state it)."""
    reachable = [site for site in results["sites"] if site["status"] in REACHABLE]
    return len(reachable), {name: sum(1 for site in reachable if _value(site, name) != UNKNOWN) for name in FIELDS}


def summary_sentence(results: dict) -> str:
    sites = results["sites"]
    count = lambda status: sum(1 for site in sites if site["status"] == status)  # noqa: E731
    unread = [(count("blocked"), "blocked"), (count("unreachable"), "unreachable"),
              (count("robots_disallowed"), "ruled out by robots.txt")]
    total_unread = sum(number for number, _ in unread)
    text = (f"{len(sites)} site{'s' if len(sites) != 1 else ''} listed: {count('ok')} read, "
            f"{count('partial')} partly read, {total_unread} not read")
    detail = ", ".join(f"{number} {label}" for number, label in unread if number)
    return text + (f" ({detail})." if detail else ".")


def _plural(number: int, word: str) -> str:
    return f"{number} {word}{'' if number == 1 else 's'}"


# --------------------------------------------------------------------------- JSON
def render_json(results: dict) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- CSV
CSV_COLUMNS = (["slug", "name", "url", "status", "status_detail", "needs_rendering", "pages_read",
                "one_liner", "categories", "target_user", "tasks", "can_execute", "multi_agent",
                "integrations", "free_tier", "starting_price", "hq_city", "hq_country"]
               + [f"{name}_source" for name in FIELDS] + [f"{name}_quote" for name in FIELDS])


def _csv_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _csv_safe(text: str) -> str:
    """Keep a spreadsheet from reading site text as a formula."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def render_csv(results: dict) -> str:
    """One row per site. Lists are joined with '; '. The <field>_source and
    <field>_quote columns hold the first piece of evidence for that field."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for site in results["sites"]:
        row = {"slug": site["slug"], "name": site["name"], "url": site["url"], "status": site["status"],
               "status_detail": site["status_detail"],
               "needs_rendering": _csv_scalar(site["needs_rendering"]) if site["status"] in REACHABLE else UNKNOWN,
               "pages_read": str(_pages_read(site))}
        for name in ("one_liner", "can_execute", "multi_agent"):
            row[name] = _csv_scalar(_value(site, name))
        for name in LIST_FIELDS:
            value = _value(site, name)
            row[name] = UNKNOWN if value == UNKNOWN else "; ".join(str(item) for item in value)
        pricing, place = _value(site, "pricing"), _value(site, "hq_location")
        row["free_tier"] = _csv_scalar(pricing.get("free_tier", UNKNOWN) if isinstance(pricing, dict) else UNKNOWN)
        row["starting_price"] = pricing.get("starting_price", UNKNOWN) if isinstance(pricing, dict) else UNKNOWN
        row["hq_city"] = place.get("city", UNKNOWN) if isinstance(place, dict) else UNKNOWN
        row["hq_country"] = place.get("country", UNKNOWN) if isinstance(place, dict) else UNKNOWN
        for name in FIELDS:
            evidence = site["fields"][name]["evidence"]
            row[f"{name}_source"] = evidence[0]["url"] if evidence else ""
            row[f"{name}_quote"] = evidence[0]["quote"] if evidence else ""
        writer.writerow({key: _csv_safe(str(value)) for key, value in row.items()})
    return buffer.getvalue()


# --------------------------------------------------------------------------- Markdown
MARKDOWN_COLUMNS = 8


def _md_cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _md_text(text: str) -> str:
    return " ".join(str(text).split()).replace("<", "&lt;").replace(">", "&gt;")


def render_markdown(results: dict) -> str:
    reachable, known = coverage(results)
    lines = ["# Agent Scout report", "",
             f"Run `{results['run_id']}`, finished {results['finished_at']}, "
             f"agent-scout {results['tool']['version']}.", "",
             summary_sentence(results), "",
             "Every value is followed by the sentence it came from and the page that sentence is on. "
             "What a site does not state is written as unknown.", "",
             "## Coverage", ""]
    for name in FIELDS:
        lines.append(f"- {FIELD_LABELS[name]}: known for {known[name]} of {reachable} reachable sites")
    lines += ["", "## Comparison", "",
              "| Product | Status | Categories | Acts by itself | Multi-agent | Pricing | Headquarters | Integrations |",
              "|---|---|---|---|---|---|---|---|"]
    for site in results["sites"]:
        integrations = _value(site, "integrations")
        count = UNKNOWN if integrations == UNKNOWN else str(len(integrations))
        cells = [f"[{_md_cell(site['name'])}]({site['url']})", STATUS_LABELS[site["status"]],
                 *(_md_cell(display(name, _value(site, name)))
                   for name in ("categories", "can_execute", "multi_agent", "pricing", "hq_location")), count]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Profiles"]
    for site in results["sites"]:
        lines += ["", f"### {_md_text(site['name'])}", "",
                  f"{site['url']} · {STATUS_LABELS[site['status']]}: {_md_text(site['status_detail'])}"]
        if site["status"] not in REACHABLE:
            lines += ["", "The site was not read, so every field is unknown."]
            continue
        for name in FIELDS:
            entry = site["fields"][name]
            lines += ["", f"**{FIELD_LABELS[name]}:** {_md_text(display(name, entry['value']))}"]
            for items, evidence in group_evidence(entry["evidence"]):
                label = f"{_md_text(', '.join(items))}: " if items else ""
                method = METHOD_LABELS.get(evidence["method"], evidence["method"])
                source = (f"[{_md_cell(_short_url(evidence['url']))}]({evidence['url']})"
                          if evidence["url"].startswith(("http://", "https://")) else _md_text(evidence["url"]))
                lines += ["", f"> {label}{_md_text(evidence['quote'])}  ", f"> {method}, {source}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- HTML
def _e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _short_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path if parts.path not in ("", "/") else ""
    return f"{parts.netloc}{path}" or url


def _link(url: str, label: str | None = None, css: str = "") -> str:
    text = _e(label if label is not None else _short_url(url))
    if urlsplit(url).scheme not in ("http", "https"):
        return f"<span>{text}</span>"
    cls = f' class="{css}"' if css else ""
    return f'<a{cls} href="{_e(url)}" rel="noopener noreferrer">{text}</a>'


def _value_html(field: str, value: Any) -> str:
    if value == UNKNOWN:
        return '<span class="unknown">unknown</span>'
    if field in LIST_FIELDS:
        return " ".join(f'<span class="tag">{_e(item)}</span>' for item in value)
    return f"<span>{_e(display(field, value))}</span>"


def group_evidence(evidence: list[dict]) -> list[tuple[list[str], dict]]:
    """Merge evidence entries that cite the same quote on the same page, so a
    sentence that supports three list values is shown once with three labels."""
    groups: list[tuple[list[str], dict]] = []
    for entry in evidence:
        for items, first in groups:
            if (first["url"], first["quote"], first["method"]) == (entry["url"], entry["quote"], entry["method"]):
                if entry.get("item"):
                    items.append(ITEM_LABELS.get(entry["item"], str(entry["item"])))
                break
        else:
            groups.append(([ITEM_LABELS.get(entry["item"], str(entry["item"]))] if entry.get("item") else [], entry))
    return groups


def _evidence_html(entry: dict) -> str:
    if not entry["evidence"]:
        return ""
    rows = []
    for items, evidence in group_evidence(entry["evidence"]):
        label = f'<span class="item">{_e(", ".join(items))}</span> ' if items else ""
        rows.append(
            f'<li class="evidence">{label}<q>{_e(evidence["quote"])}</q> '
            f'<span class="source">{_link(evidence["url"])} '
            f'<span class="method">{_e(METHOD_LABELS.get(evidence["method"], evidence["method"]))}</span></span></li>')
    return f'<ul class="evidence-list">{"".join(rows)}</ul>'


def _data_attrs(site: dict) -> str:
    return (f'data-slug="{_e(site["slug"])}" data-categories="{_e("|".join(_categories(site)))}" '
            f'data-country="{_e(_country(site))}"')


def _table_row(site: dict) -> str:
    name = (f'<a class="open-card" href="#card-{_e(site["slug"])}">{_e(site["name"])}</a>'
            f'<span class="host">{_e(_short_url(site["url"]))}</span>')
    if site["status"] not in REACHABLE:
        return (f'<tr class="not-read status-{_e(site["status"])}" {_data_attrs(site)}>'
                f'<th scope="row">{name}</th>'
                f'<td colspan="7" class="reason"><strong>{_e(STATUS_LABELS[site["status"]].capitalize())}.</strong> '
                f'{_e(site["status_detail"])}. The site was not read, so every field is unknown.</td></tr>')
    note = ""
    if site["needs_rendering"]:
        note = '<span class="flag">JavaScript shell: only its head data was read</span>'
    elif site["status"] == "partial":
        note = f'<span class="flag">partly read: {_e(site["status_detail"])}</span>'
    def cell(field: str) -> str:
        """A known value is a link to the row of the profile that holds its quote."""
        value = _value(site, field)
        if value == UNKNOWN:
            return '<td><span class="unknown">unknown</span></td>'
        if field == "integrations":
            shown = ", ".join(_e(item) for item in value[:3])
            more = f' <span class="more">and {len(value) - 3} more</span>' if len(value) > 3 else ""
            inner = f"{shown}{more}"
        else:
            inner = _value_html(field, value)
        return (f'<td><a class="to-evidence" href="#card-{_e(site["slug"])}-{field}" '
                f'title="Show the quote this rests on">{inner}</a></td>')

    cells = "".join(cell(field) for field in TABLE_FIELDS)
    return (f'<tr class="status-{_e(site["status"])}" {_data_attrs(site)}>'
            f'<th scope="row">{name}{note}</th>{cells}</tr>')


def _card(site: dict) -> str:
    status = f'<span class="status status-{_e(site["status"])}">{_e(STATUS_LABELS[site["status"]])}</span>'
    head = (f'<summary><span class="name">{_e(site["name"])}</span> {status} '
            f'<span class="host">{_e(_short_url(site["url"]))}</span></summary>')
    if site["status"] not in REACHABLE:
        body = (f'<p class="reason"><strong>{_e(STATUS_LABELS[site["status"]].capitalize())}.</strong> '
                f'{_e(site["status_detail"])}.</p>'
                f'<p class="reason">The site was not read, so every field is unknown. '
                f'{_link(site["url"], "Open the site")}</p>')
        return f'<details class="card not-read" id="card-{_e(site["slug"])}" {_data_attrs(site)}>{head}{body}</details>'
    rows = []
    for field in FIELDS:
        entry = site["fields"][field]
        rows.append(f'<div class="field" id="card-{_e(site["slug"])}-{field}" data-field="{field}">'
                    f'<dt>{_e(FIELD_LABELS[field])}</dt>'
                    f'<dd><div class="value">{_value_html(field, entry["value"])}</div>{_evidence_html(entry)}</dd></div>')
    pages = _plural(_pages_read(site), "page") + " read"
    note = f'<p class="crawl-note">{_e(site["status_detail"])}. {_link(site["url"], "Open the site")}</p>' \
        if site["status"] == "partial" else f'<p class="crawl-note">{_e(pages)}. {_link(site["url"], "Open the site")}</p>'
    return (f'<details class="card" id="card-{_e(site["slug"])}" {_data_attrs(site)}>{head}{note}'
            f'<dl class="fields">{"".join(rows)}</dl></details>')


_CSS = """
:root{--paper:#f3f5f1;--sheet:#fff;--ink:#17201b;--muted:#5f6a63;--rule:#cdd5ce;--link:#2437c8;
--mark:#ffec80;--warn:#8a3b00;--warn-bg:#fff0dd;--sans:"Inter","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
--serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,"DejaVu Serif",serif}
*{box-sizing:border-box}
html{background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans);-webkit-text-size-adjust:100%}
body{margin:0 auto;max-width:1240px;padding:36px 32px 80px}
a{color:var(--link);text-underline-offset:2px}
a:focus-visible,summary:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid var(--link);outline-offset:2px}
h1{font-size:40px;line-height:1.05;letter-spacing:-.02em;margin:0 0 14px;font-weight:700}
h2{font-size:20px;line-height:1.2;margin:44px 0 6px;font-weight:650}
#summary{font-size:21px;line-height:1.35;margin:0 0 8px;max-width:60ch}
.run{color:var(--muted);margin:0;max-width:78ch}
.section-note{color:var(--muted);margin:0 0 14px;max-width:78ch}
#coverage ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(9,1fr);gap:0 18px;border-top:2px solid var(--ink)}
#coverage li{padding:10px 0 0}
.cov-label{display:block;font-weight:600;font-size:13px}
.cov-count{display:block;font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.cov-bar{display:flex;gap:3px;margin:7px 0 5px}
.cov-bar i{flex:1;height:9px;border:1.5px solid var(--ink);background:transparent}
.cov-bar i.on{background:var(--ink)}
.filters{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center;margin:0 0 12px}
.filters label{font-weight:600;font-size:14px}
select,button{font:inherit;font-size:14px;color:var(--ink);background:var(--sheet);border:1.5px solid var(--ink);border-radius:3px;padding:5px 10px;margin-left:6px}
button{margin-left:auto;cursor:pointer}
#filter-note{flex-basis:100%;margin:0;color:var(--warn);font-size:14px}
table{width:100%;border-collapse:collapse;background:var(--sheet);font-size:14px;line-height:1.4;table-layout:fixed}
thead th{text-align:left;font-size:13px;font-weight:650;padding:10px 12px;border-bottom:2px solid var(--ink);vertical-align:bottom}
tbody th,tbody td{padding:11px 12px;border-bottom:1px solid var(--rule);vertical-align:top;text-align:left;overflow-wrap:anywhere}
tbody th{font-weight:600}
col.c-name{width:19%}col.c-cat{width:15%}col.c-user{width:13%}col.c-exec{width:8%}col.c-multi{width:8%}col.c-price{width:14%}col.c-hq{width:11%}col.c-int{width:12%}
.open-card{font-weight:650;font-size:15px}
a.to-evidence{color:inherit;text-decoration:underline dotted var(--muted);text-underline-offset:3px;display:block}
a.to-evidence:hover{color:var(--link);text-decoration:underline solid}
a.to-evidence .tag{text-decoration:none}
.field:target{background:#fffbe0;box-shadow:-12px 0 0 #fffbe0,12px 0 0 #fffbe0}
html{scroll-padding-top:16px}
.host{display:block;color:var(--muted);font-weight:400;font-size:12.5px}
.flag{display:block;margin-top:4px;color:var(--warn);font-weight:500;font-size:12.5px}
.unknown{color:var(--muted);font-style:italic}
.tag{display:inline-block;margin:0 4px 3px 0;padding:0 7px;border:1px solid var(--rule);border-radius:10px;white-space:nowrap}
.more{color:var(--muted);white-space:nowrap}
tr.not-read th,tr.not-read td,details.not-read{background:repeating-linear-gradient(135deg,var(--warn-bg) 0 9px,#ffe6c7 9px 10px)}
td.reason,p.reason{color:var(--warn)}
td.reason strong,p.reason strong{font-weight:700}
details.card{background:var(--sheet);border-top:2px solid var(--ink);margin:0 0 14px;padding:0 20px}
details.card>summary{list-style:none;cursor:pointer;padding:14px 0;display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline}
details.card>summary::-webkit-details-marker{display:none}
details.card>summary::before{content:"+";font-weight:700;width:14px;display:inline-block}
details.card[open]>summary::before{content:"\\2212"}
summary .name{font-size:19px;font-weight:650}
summary .host{display:inline}
.status{font-size:12.5px;font-weight:600;padding:1px 8px;border:1.5px solid var(--ink);border-radius:3px}
.status-partial.status,.status-blocked.status,.status-unreachable.status,.status-robots_disallowed.status{color:var(--warn);border-color:var(--warn);background:var(--warn-bg)}
.crawl-note{margin:0 0 6px 28px;color:var(--muted)}
p.reason{margin:0 0 12px 28px}
dl.fields{margin:0 0 18px 28px}
.field{display:grid;grid-template-columns:150px 1fr;gap:0 20px;padding:11px 0;border-top:1px solid var(--rule)}
.field dt{font-weight:600;font-size:14px}
.field dd{margin:0}
.value{font-size:15px}
.evidence-list{list-style:none;margin:7px 0 0;padding:0}
.evidence{margin:5px 0 0;font-size:14px;line-height:1.6}
.evidence .item{font-weight:600;font-size:12.5px;margin-right:2px}
q{quotes:none;font-family:var(--serif);font-size:15.5px;background:var(--mark);padding:1px 3px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.source{white-space:nowrap;font-size:13px;margin-left:6px}
.method{color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-size:13px;max-width:78ch}
@media (max-width:900px){body{padding:20px 14px 60px}h1{font-size:30px}#coverage ul{grid-template-columns:repeat(3,1fr);gap:8px 18px}
table{table-layout:auto;display:block;overflow-x:auto}.field{grid-template-columns:1fr}.source{white-space:normal}}
@media print{details.card{break-inside:avoid}.filters{display:none}}
"""

_JS = """
(function () {
  var category = document.getElementById('filter-category');
  var country = document.getElementById('filter-country');
  var note = document.getElementById('filter-note');
  function apply() {
    var wantCategory = category.value, wantCountry = country.value, hidden = 0, total = 0;
    document.querySelectorAll('[data-slug]').forEach(function (element) {
      var categories = (element.dataset.categories || '').split('|');
      var show = (!wantCategory || categories.indexOf(wantCategory) >= 0) &&
                 (!wantCountry || element.dataset.country === wantCountry);
      element.hidden = !show;
      if (element.tagName === 'TR') { total += 1; if (!show) { hidden += 1; } }
    });
    note.hidden = !(wantCategory || wantCountry);
    note.textContent = hidden + ' of ' + total + ' sites are hidden. A site whose category or country ' +
      'is unknown cannot match a filter, so it is hidden too.';
  }
  category.addEventListener('change', apply);
  country.addEventListener('change', apply);
  document.querySelectorAll('a.open-card, a.to-evidence').forEach(function (link) {
    link.addEventListener('click', function () {
      var target = document.querySelector(link.getAttribute('href'));
      var card = target && target.closest('details.card');
      if (card) { card.open = true; }
    });
  });
  var toggle = document.getElementById('open-all');
  toggle.addEventListener('click', function () {
    var cards = document.querySelectorAll('details.card');
    var open = toggle.dataset.open !== 'yes';
    cards.forEach(function (card) { card.open = open; });
    toggle.dataset.open = open ? 'yes' : '';
    toggle.textContent = open ? 'Close all profiles' : 'Open all profiles';
  });
})();
"""


def render_html(results: dict) -> str:
    """The whole report as one HTML document with inline CSS and JS."""
    sites = results["sites"]
    reachable, known = coverage(results)
    coverage_items = []
    for name in FIELDS:
        bar = "".join(f'<i{" class=on" if index < known[name] else ""}></i>' for index in range(reachable))
        coverage_items.append(
            f'<li data-field="{name}"><span class="cov-label">{_e(FIELD_LABELS[name])}</span>'
            f'<span class="cov-bar" aria-hidden="true">{bar}</span>'
            f'<span class="cov-count">{known[name]} of {reachable}</span></li>')
    categories = sorted({category for site in sites for category in _categories(site)})
    countries = sorted({_country(site) for site in sites if _country(site)})
    options = lambda values, every: f'<option value="">{every}</option>' + "".join(  # noqa: E731
        f'<option value="{_e(value)}">{_e(value)}</option>' for value in values)
    llm = results["settings"].get("llm", {})
    llm_note = (f" An LLM pass ({_e(llm.get('provider'))}, {_e(llm.get('model'))}) added values marked "
                f"“LLM, quote verified”; each was kept only because its quote was found in the fetched text."
                if llm.get("enabled") else "")
    finished = str(results["finished_at"]).replace("T", " ").replace("Z", " UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Scout report</title>
<style>{_CSS}</style>
</head>
<body>
<header>
<h1>Agent Scout report</h1>
<p id="summary">{_e(summary_sentence(results))}</p>
<p class="run">Every value links to the sentence it came from: select a value in the table to see its quote
and the page the quote is on. What a site does not state is shown as
<span class="unknown">unknown</span>. Run {_e(results["run_id"])}, finished {_e(finished)},
agent-scout {_e(results["tool"]["version"])}.{llm_note}</p>
</header>

<section id="coverage">
<h2>What the reachable sites state</h2>
<p class="section-note">Each field is counted as known for k of the {reachable} reachable
{'site' if reachable == 1 else 'sites'} (read or partly read). Sites that were not read are left out of the count.</p>
<ul>{"".join(coverage_items)}</ul>
</section>

<section>
<h2>Comparison</h2>
<div class="filters">
<label>Category<select id="filter-category">{options(categories, "All categories")}</select></label>
<label>Country<select id="filter-country">{options(countries, "All countries")}</select></label>
<button type="button" id="open-all">Open all profiles</button>
<p id="filter-note" hidden></p>
</div>
<table id="comparison">
<colgroup><col class="c-name"><col class="c-cat"><col class="c-user"><col class="c-exec"><col class="c-multi"><col class="c-price"><col class="c-hq"><col class="c-int"></colgroup>
<thead><tr><th scope="col">Product</th><th scope="col">Categories</th><th scope="col">Target users</th>
<th scope="col">Acts by itself</th><th scope="col">Multi-agent</th><th scope="col">Pricing</th>
<th scope="col">Headquarters</th><th scope="col">Integrations</th></tr></thead>
<tbody>
{"".join(_table_row(site) for site in sites)}
</tbody>
</table>
</section>

<section id="profiles">
<h2>Profiles</h2>
<p class="section-note">Open a profile to see each value with the quoted text behind it and the page the quote is on.</p>
{"".join(_card(site) for site in sites)}
</section>

<footer>Written by agent-scout {_e(results["tool"]["version"])} from the products’ own public pages,
fetched with the user agent “{_e(results["settings"]["user_agent"])}”. Keyword rules decide the vocabulary fields,
so a value can be wrong; the quote beside it shows what it rests on.</footer>
<script>{_JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- files
WRITERS: list[tuple[str, Callable[[dict], str]]] = [
    ("results.json", render_json),
    ("results.csv", render_csv),
    ("report.md", render_markdown),
    ("report.html", render_html),
]


def write_all(results: dict[str, Any], out_dir: Path) -> list[Path]:
    """Write every report into ``out_dir`` and return the paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, render in WRITERS:
        with obs.span("report", file=filename) as span:
            path = out_dir / filename
            path.write_text(render(results), encoding="utf-8", newline="\n")
            span.context["bytes"] = path.stat().st_size
            paths.append(path)
    return paths
