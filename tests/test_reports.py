"""Report rendering: JSON, CSV, Markdown and the self-contained HTML page."""

import csv
import io
import json
import re

import pytest
from bs4 import BeautifulSoup

from agent_scout import reports
from agent_scout.model import FIELDS, UNKNOWN

from conftest import launch_chromium

U = UNKNOWN


def ev(quote, url="https://acme.test/", method="sentence", item=None):
    return {"item": item, "url": url, "quote": quote, "method": method}


def site(slug, status="ok", fields=None, **extra):
    base = {name: {"value": U, "evidence": []} for name in FIELDS}
    base.update(fields or {})
    return {"slug": slug, "name": extra.pop("name", slug.title()), "url": f"https://{slug}.test/",
            "final_url": f"https://{slug}.test/" if status in ("ok", "partial") else None,
            "status": status, "status_detail": extra.pop("detail", "1 page read"),
            "needs_rendering": extra.pop("needs_rendering", False),
            "robots": {"state": "ok", "http_status": 200, "crawl_delay": None},
            "pages": [], "llm": None, "fields": base}


def document(sites):
    return {"schema_version": "1.0", "tool": {"name": "agent-scout", "version": "0.1.0"}, "run_id": "r1",
            "started_at": "2026-11-10T00:00:00Z", "finished_at": "2026-11-10T00:01:00Z",
            "settings": {"page_budget": 6, "delay_seconds": 1.5, "max_crawl_delay_seconds": 30,
                         "timeout_seconds": 20, "user_agent": "agent-scout/0.1.0", "llm": {"enabled": False,
                                                                                         "provider": None, "model": None}},
            "sites": sites}


FULL = site("acme", fields={
    "one_liner": {"value": "Acme sends campaigns.", "evidence": [ev("Acme sends campaigns.", method="meta")]},
    "categories": {"value": ["email marketing", "seo"], "evidence": [
        ev("Email marketing on autopilot", method="heading", item="email marketing"),
        ev("SEO built in", method="heading", item="seo")]},
    "target_user": {"value": ["agencies"], "evidence": [ev("Built for agencies.", item="agencies")]},
    "tasks": {"value": ["write copy"], "evidence": [ev("It writes ad copy.", item="write copy")]},
    "can_execute": {"value": True, "evidence": [ev("It sends each campaign automatically.")]},
    "multi_agent": {"value": True, "evidence": [ev("A team of agents.")]},
    "integrations": {"value": ["Slack", "HubSpot"], "evidence": [
        ev("Slack logo", url="https://acme.test/integrations", method="link", item="Slack"),
        ev("HubSpot logo", url="https://acme.test/integrations", method="link", item="HubSpot")]},
    "pricing": {"value": {"free_tier": True, "starting_price": "$49/month"}, "evidence": [
        ev("Free | $0", url="https://acme.test/pricing", method="table", item="free_tier"),
        ev("Pro | $49/month", url="https://acme.test/pricing", method="table", item="starting_price")]},
    "hq_location": {"value": {"city": "Austin", "country": "United States"}, "evidence": [
        ev("Based in Austin, Texas.", url="https://acme.test/about")]},
})
DRAFTS = site("quill", fields={
    "can_execute": {"value": False, "evidence": [ev("Quill only drafts.")]},
    "categories": {"value": ["seo"], "evidence": [ev("SEO built in", method="heading", item="seo")]},
    "pricing": {"value": {"free_tier": False, "starting_price": U}, "evidence": [
        ev("There is no free plan.", item="free_tier")]},
    "hq_location": {"value": {"city": "Berlin", "country": U}, "evidence": [ev("Based in Berlin.")]},
})
EMPTY = site("empty")
BLOCKED = site("wall", status="blocked", detail="HTTP 403 at https://wall.test/; the tool does not try to get around it")
SHELL = site("shell", status="partial", needs_rendering=True,
             detail="0 pages read; 1 page needs JavaScript rendering and was not interpreted")
GONE = site("gone", status="unreachable", detail="the start URL could not be read (connection_error)")
ROBOTS = site("shy", status="robots_disallowed", detail="robots.txt disallows https://shy.test/")
ALL = document([FULL, DRAFTS, EMPTY, BLOCKED, SHELL, GONE, ROBOTS])

DENIALS = re.compile(r"\b(no|none|false|n/a|nil|never|zero)\b", re.IGNORECASE)


def visible_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(" ")


# ------------------------------------------------------------------ unknown is never a denial
@pytest.mark.parametrize("fmt", ["html", "md", "csv"])
def test_unknown_is_never_rendered_as_no_none_or_false(fmt):
    doc = document([EMPTY, SHELL, BLOCKED, GONE, ROBOTS])
    def csv_field_cells():
        # every column except the crawl facts (status, needs_rendering, pages_read), which are known
        rows = csv.DictReader(io.StringIO(reports.render_csv(doc)))
        crawl_facts = ("slug", "name", "url", "status", "status_detail", "needs_rendering", "pages_read")
        return " ".join(value for row in rows for key, value in row.items() if key not in crawl_facts)

    text = {"html": lambda: visible_text(reports.render_html(doc)),
            "md": lambda: reports.render_markdown(doc),
            "csv": csv_field_cells}[fmt]()
    assert not DENIALS.search(text), DENIALS.search(text).group(0)
    assert "unknown" in text


@pytest.mark.parametrize("field, value, expected", [
    ("can_execute", U, "unknown"), ("can_execute", True, "yes"), ("can_execute", False, "drafts only"),
    ("multi_agent", U, "unknown"), ("multi_agent", True, "yes"),
    ("categories", U, "unknown"), ("categories", ["seo", "advertising"], "seo, advertising"),
    ("pricing", U, "unknown"),
    ("pricing", {"free_tier": True, "starting_price": "$49/month"}, "free plan or trial; from $49/month"),
    ("pricing", {"free_tier": U, "starting_price": "$49/month"}, "free plan or trial unknown; from $49/month"),
    ("pricing", {"free_tier": False, "starting_price": U}, "states it has no free plan or trial; price unknown"),
    ("hq_location", U, "unknown"),
    ("hq_location", {"city": "Austin", "country": "United States"}, "Austin, United States"),
    ("hq_location", {"city": "Berlin", "country": U}, "Berlin (country unknown)"),
    ("hq_location", {"city": U, "country": "Germany"}, "Germany (city unknown)"),
])
def test_display_values(field, value, expected):
    assert reports.display(field, value) == expected


def test_a_stated_false_is_shown_as_a_statement_not_as_unknown():
    text = visible_text(reports.render_html(document([DRAFTS])))
    assert "drafts only" in text
    assert "states it has no free plan or trial" in text


# ------------------------------------------------------------------ HTML
def test_html_is_one_self_contained_file():
    html = reports.render_html(ALL)
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.find_all("link")
    assert not [tag for tag in soup.find_all(src=True)]
    assert "@import" not in html
    assert not re.search(r"url\(\s*['\"]?(?!data:)", html)
    assert len(soup.find_all("style")) == 1 and len(soup.find_all("script")) == 1
    assert soup.find("meta", attrs={"charset": True})


def test_html_summary_counts_and_honest_coverage():
    soup = BeautifulSoup(reports.render_html(ALL), "html.parser")
    summary = soup.find(id="summary").get_text(" ", strip=True)
    assert "7 sites" in summary
    assert "3 read" in summary and "1 partly read" in summary and "3 not read" in summary
    coverage = {row["data-field"]: row.get_text(" ", strip=True) for row in soup.select("#coverage [data-field]")}
    assert set(coverage) == set(FIELDS)
    # reachable sites are the four with status ok or partial
    assert "1 of 4" in coverage["one_liner"]
    assert "2 of 4" in coverage["categories"]
    assert "2 of 4" in coverage["can_execute"]         # true and false are both stated values
    assert "1 of 4" in coverage["multi_agent"]
    assert "reachable" in soup.find(id="coverage").get_text(" ")


def test_html_comparison_table_has_a_row_per_site_and_marks_unread_sites():
    soup = BeautifulSoup(reports.render_html(ALL), "html.parser")
    rows = soup.select("#comparison tbody tr")
    assert [row["data-slug"] for row in rows] == ["acme", "quill", "empty", "wall", "shell", "gone", "shy"]
    by_slug = {row["data-slug"]: row for row in rows}
    assert "not-read" in by_slug["wall"]["class"] and "blocked" in by_slug["wall"].get_text(" ").lower()
    assert "HTTP 403" in by_slug["wall"].get_text(" ")
    assert "not-read" in by_slug["gone"]["class"] and "not-read" in by_slug["shy"]["class"]
    assert "robots.txt" in by_slug["shy"].get_text(" ")
    assert "JavaScript" in by_slug["shell"].get_text(" ")
    assert "not-read" not in by_slug["acme"]["class"]


def test_html_card_shows_every_value_with_its_quote_and_source_link():
    soup = BeautifulSoup(reports.render_html(ALL), "html.parser")
    card = soup.find(id="card-acme")
    for name in FIELDS:
        row = card.find(attrs={"data-field": name})
        assert row is not None, name
        for evidence in FULL["fields"][name]["evidence"]:
            quote = row.find("q", string=evidence["quote"])
            assert quote is not None, (name, evidence["quote"])
            link = quote.find_parent(class_="evidence").find("a")
            assert link["href"] == evidence["url"]
            assert "noopener" in link["rel"]
    wall = soup.find(id="card-wall")
    assert "not-read" in wall["class"] and "HTTP 403" in wall.get_text(" ")
    assert not wall.find("q")


def test_html_filters_list_the_categories_and_countries_present():
    soup = BeautifulSoup(reports.render_html(ALL), "html.parser")
    categories = [option["value"] for option in soup.select("#filter-category option")]
    countries = [option["value"] for option in soup.select("#filter-country option")]
    assert categories == ["", "email marketing", "seo"]
    assert countries == ["", "United States"]
    row = soup.select_one("#comparison tr[data-slug=acme]")
    assert row["data-categories"] == "email marketing|seo" and row["data-country"] == "United States"
    assert soup.select_one("#comparison tr[data-slug=wall]")["data-categories"] == ""


def test_html_escapes_everything_that_came_from_a_site():
    hostile = site("x", name='<script>alert("n")</script>', fields={
        "one_liner": {"value": "<img src=x onerror=alert(1)>", "evidence": [
            ev('"><script>alert(2)</script>', url="javascript:alert(3)", method="meta")]},
        "integrations": {"value": ["<b>Slack</b>"], "evidence": [ev("<b>Slack</b> logo", url="https://x.test/?a=1&b=<2>",
                                                                   method="link", item="<b>Slack</b>")]},
    })
    html = reports.render_html(document([hostile]))
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.find_all("script")) == 1                   # only the report's own script
    assert not soup.find_all("img") and not soup.find_all("b")
    assert not soup.find_all("a", href=re.compile(r"^\s*javascript:", re.IGNORECASE))
    assert '<script>alert("n")</script>' in soup.get_text()    # shown as text


# ------------------------------------------------------------------ CSV
def test_csv_columns_and_rows():
    rows = list(csv.DictReader(io.StringIO(reports.render_csv(ALL))))
    assert len(rows) == 7
    assert list(rows[0])[:8] == ["slug", "name", "url", "status", "status_detail", "needs_rendering",
                                 "pages_read", "one_liner"]
    assert set(reports.CSV_COLUMNS) == set(rows[0])
    acme = rows[0]
    assert acme["categories"] == "email marketing; seo"
    assert acme["can_execute"] == "true" and acme["multi_agent"] == "true"
    assert (acme["free_tier"], acme["starting_price"]) == ("true", "$49/month")
    assert (acme["hq_city"], acme["hq_country"]) == ("Austin", "United States")
    assert acme["pricing_source"] == "https://acme.test/pricing"
    assert acme["can_execute_quote"] == "It sends each campaign automatically."
    quill = rows[1]
    assert quill["can_execute"] == "false" and quill["free_tier"] == "false" and quill["hq_country"] == "unknown"
    wall = rows[3]
    assert wall["status"] == "blocked" and wall["one_liner"] == "unknown" and wall["one_liner_source"] == ""
    # whether a page needs rendering is only known for sites that were read
    assert (acme["needs_rendering"], wall["needs_rendering"], rows[4]["needs_rendering"]) == ("false", "unknown", "true")


def test_csv_cells_cannot_start_a_formula():
    doc = document([site("x", fields={"one_liner": {"value": "=HYPERLINK(\"http://evil\")", "evidence": []}})])
    row = next(csv.DictReader(io.StringIO(reports.render_csv(doc))))
    assert row["one_liner"].startswith("'=")


# ------------------------------------------------------------------ Markdown
def test_markdown_report():
    text = reports.render_markdown(ALL)
    assert text.startswith("# Agent Scout report")
    table_rows = [line for line in text.splitlines() if line.startswith("| ") and "acme.test" in line]
    assert table_rows
    assert "> It sends each campaign automatically." in text
    assert "(https://acme.test/pricing)" in text
    assert "blocked" in text and "HTTP 403" in text
    assert "known for 2 of 4 reachable sites" in text


def test_markdown_escapes_pipes_and_newlines_in_table_cells():
    doc = document([site("x", fields={"categories": {"value": ["a|b"], "evidence": []}}, name="A | B")])
    row = next(line for line in reports.render_markdown(doc).splitlines() if line.startswith("| [A"))
    assert row.count(" | ") == reports.MARKDOWN_COLUMNS - 1


# ------------------------------------------------------------------ files
def test_write_all_writes_four_files_and_logs_each(tmp_path, events):
    paths = reports.write_all(ALL, tmp_path / "out")
    assert [path.name for path in paths] == ["results.json", "results.csv", "report.md", "report.html"]
    assert json.loads(paths[0].read_text(encoding="utf-8"))["schema_version"] == "1.0"
    done = [e for e in events() if e["stage"] == "report" and e["event"] == "success"]
    assert [e["context"]["file"] for e in done] == ["results.json", "results.csv", "report.md", "report.html"]
    assert all(e["context"]["bytes"] > 0 for e in done)


# ------------------------------------------------------------------ in a browser (skipped without Chromium)
@pytest.fixture(scope="module")
def browser_page(tmp_path_factory):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path_factory.mktemp("html") / "report.html"
    path.write_text(reports.render_html(ALL), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        requests_made = []
        page.on("request", lambda request: requests_made.append(request.url))
        page.goto(path.as_uri())
        page.requests_made = requests_made
        yield page
        browser.close()


def test_browser_makes_no_external_request_and_fits_1280(browser_page):
    assert all(url.startswith("file:") for url in browser_page.requests_made)
    assert browser_page.evaluate("document.documentElement.scrollWidth") <= 1280


def test_browser_filters_and_card_opening(browser_page):
    page = browser_page
    visible = lambda: page.eval_on_selector_all(  # noqa: E731
        "#comparison tbody tr", "rows => rows.filter(r => !r.hidden).map(r => r.dataset.slug)")
    assert len(visible()) == 7
    page.select_option("#filter-category", "seo")
    assert visible() == ["acme", "quill"]
    assert "5" in page.inner_text("#filter-note")
    page.select_option("#filter-country", "United States")
    assert visible() == ["acme"]
    page.select_option("#filter-category", "")
    page.select_option("#filter-country", "")
    assert len(visible()) == 7
    assert not page.is_visible("#card-acme q")
    page.click("#comparison tr[data-slug=acme] a.open-card")
    assert page.is_visible("#card-acme q")


def test_one_quote_supporting_several_values_is_shown_once():
    shared = ev("Email and SEO in one agent.", method="meta")
    doc = document([site("x", fields={"categories": {"value": ["email marketing", "seo"], "evidence": [
        {**shared, "item": "email marketing"}, {**shared, "item": "seo"}]}})])
    soup = BeautifulSoup(reports.render_html(doc), "html.parser")
    row = soup.find(id="card-x").find(attrs={"data-field": "categories"})
    assert len(row.find_all("q")) == 1
    assert row.find(class_="item").get_text() == "email marketing, seo"
    assert reports.render_markdown(doc).count("> email marketing, seo: Email and SEO in one agent.") == 1


class _NoBrowser:
    class chromium:
        @staticmethod
        def launch():
            raise RuntimeError("Executable doesn't exist at /somewhere/chrome\nmore detail on later lines")


def test_a_missing_browser_is_skipped_with_the_reason_and_the_fix(monkeypatch):
    monkeypatch.delenv("AGENT_SCOUT_REQUIRE_BROWSER", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        launch_chromium(_NoBrowser)
    message = str(skipped.value)
    assert "Executable doesn't exist" in message and "python -m playwright install chromium" in message
    assert "more detail" not in message


def test_a_missing_browser_is_a_failure_where_one_is_required(monkeypatch):
    monkeypatch.setenv("AGENT_SCOUT_REQUIRE_BROWSER", "1")
    with pytest.raises(pytest.fail.Exception):
        launch_chromium(_NoBrowser)
