"""Crawling the bundled fictional sites end to end (local servers only)."""

import pytest

from agent_scout.config import Config
from agent_scout.crawl import crawl_site
from agent_scout.fetch import Fetcher
from agent_scout.inputs import SiteInput


@pytest.fixture
def crawl(fixture_sites, fake_time):
    def run(slug, **settings):
        settings.setdefault("delay_seconds", 0.0)
        site = fixture_sites[slug]
        del site.requests[:]
        fetcher = Fetcher(Config(**settings), sleep=fake_time.sleep, clock=fake_time.clock)
        result = crawl_site(SiteInput(slug=slug, name=site.name, url=site.url), fetcher, fetcher.config)
        return result, site
    return run


def paths(result):
    return [record.final_url.split("/", 3)[3] for record in result.records if record.outcome == "fetched"]


def test_ok_site_reads_homepage_then_one_page_per_topic(crawl):
    result, site = crawl("northwind")
    assert result.status == "ok"
    assert paths(result) == ["", "features", "integrations", "pricing", "about", "contact"]
    assert site.paths() == ["/robots.txt", "/", "/features", "/integrations", "/pricing", "/about", "/contact"]
    assert all(record.encoding == "gzip" for record in result.records)
    assert len(result.pages) == 6 and not result.needs_rendering


def test_page_budget_is_respected(crawl):
    result, site = crawl("northwind", page_budget=2)
    assert paths(result) == ["", "features"]
    assert site.paths() == ["/robots.txt", "/", "/features"]


def test_robots_disallowed_pages_are_recorded_but_never_requested(crawl):
    result, site = crawl("northwind", page_budget=9)
    skipped = {r.url.split("/", 3)[3] for r in result.records if r.outcome == "robots_disallowed"}
    assert skipped == {"customers/stories", "internal/roadmap"}
    assert not any(path.startswith(("/customers", "/internal")) for path in site.paths())
    assert result.status == "ok"       # honouring robots.txt is not a failure


def test_specific_robots_group_crawl_delay_brotli_and_redirect(crawl, fake_time):
    result, site = crawl("orbitfleet", delay_seconds=0.25)
    assert result.status == "ok"
    assert paths(result) == ["", "platform", "pricing", "about", "contact", "customers"]
    redirected = next(r for r in result.records if r.final_url.endswith("/platform"))
    assert redirected.url.endswith("/features")
    assert all(record.encoding == "br" for record in result.records)
    assert result.robots["crawl_delay"] == 0.5
    # robots.txt, six pages and one redirect hop: seven waits of the Crawl-delay
    assert fake_time.sleeps == [0.5] * 7
    assert not any(path.startswith("/drafts") for path in site.paths())


def test_non_utf8_site_is_decoded(crawl):
    result, _ = crawl("quillmate")
    assert result.status == "ok"
    assert paths(result) == ["", "product", "pricing", "about", "contact"]
    assert {record.charset for record in result.records} == {"windows-1252"}
    home = result.pages[0]
    assert home.meta["description"].endswith("brand’s voice – for marketing teams and creators.")


def test_403_everywhere_is_blocked_after_two_requests(crawl):
    result, site = crawl("palisade")
    assert result.status == "blocked"
    assert "403" in result.detail
    assert result.pages == []
    assert site.paths() == ["/robots.txt", "/"]        # robots 403 = no rules; homepage 403 = stop


def test_robots_500_rules_the_site_out(crawl):
    result, site = crawl("tessera")
    assert result.status == "robots_disallowed"
    assert "500" in result.detail
    assert result.pages == []
    assert site.paths() == ["/robots.txt", "/robots.txt"]   # one retry, then no page is requested


def test_javascript_shell_is_partial_and_flagged(crawl):
    result, site = crawl("glimmer")
    assert result.status == "partial"
    assert result.needs_rendering is True
    assert [record.outcome for record in result.records] == ["needs_rendering"]
    assert "JavaScript" in result.detail
    assert site.paths() == ["/robots.txt", "/"]        # the shell has no links to follow


def test_unreachable_host(fake_time):
    fetcher = Fetcher(Config(delay_seconds=0, timeout_seconds=2), sleep=fake_time.sleep, clock=fake_time.clock)
    result = crawl_site(SiteInput("gone", None, "http://127.0.0.1:9/"), fetcher, fetcher.config)
    assert result.status == "unreachable"
    assert result.pages == []


def test_homepage_404_is_unreachable(scripted, make_fetcher):
    fetcher = make_fetcher()
    result = crawl_site(SiteInput("s", None, scripted.base + "/"), fetcher, fetcher.config)
    assert result.status == "unreachable"
    assert "404" in result.detail


def test_homepage_disallowed(scripted, make_fetcher):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nDisallow: /\n")
    fetcher = make_fetcher()
    result = crawl_site(SiteInput("s", None, scripted.base + "/"), fetcher, fetcher.config)
    assert result.status == "robots_disallowed"
    assert scripted.paths() == ["/robots.txt"]


def test_block_on_a_later_page_ends_the_site_as_blocked(scripted, make_fetcher):
    from conftest import html_page
    body = "<p>" + "Words about the product. " * 20 + "</p><a href='/features'>Features</a><a href='/pricing'>Pricing</a>"
    scripted.route("/", body=html_page(body)).route("/features", status=403, body="no")
    scripted.route("/pricing", body=html_page(body))
    fetcher = make_fetcher()
    result = crawl_site(SiteInput("s", None, scripted.base + "/"), fetcher, fetcher.config)
    assert result.status == "blocked"
    assert result.pages == []                       # nothing is reported about a site that blocks us
    assert "/pricing" not in scripted.paths()       # and no further request is made


def test_failed_subpage_makes_the_site_partial(scripted, make_fetcher):
    from conftest import html_page
    body = "<p>" + "Words about the product. " * 20 + "</p><a href='/features'>Features</a><a href='/pricing'>Pricing</a>"
    scripted.route("/", body=html_page(body)).route("/pricing", body=html_page(body))
    fetcher = make_fetcher()
    result = crawl_site(SiteInput("s", None, scripted.base + "/"), fetcher, fetcher.config)
    assert result.status == "partial"
    assert [r.outcome for r in result.records] == ["fetched", "error", "fetched"]
    assert len(result.pages) == 2


def test_homepage_redirect_to_another_host_moves_the_site(scripted, make_fetcher):
    from conftest import ScriptedServer, html_page
    other = ScriptedServer()
    try:
        body = "<p>" + "Words about the product. " * 20 + "</p><a href='/pricing'>Pricing</a>"
        other.route("/", body=html_page(body)).route("/pricing", body=html_page(body))
        scripted.route("/", status=301, headers={"Location": other.base + "/"})
        fetcher = make_fetcher()
        result = crawl_site(SiteInput("s", None, scripted.base + "/"), fetcher, fetcher.config)
        assert result.status == "ok"
        assert result.final_url == other.base + "/"
        assert other.paths() == ["/robots.txt", "/", "/pricing"]
    finally:
        other.stop()
