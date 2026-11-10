"""Choosing which pages of a site to read after the homepage."""

from agent_scout.config import Config
from agent_scout.links import same_site, select_links
from agent_scout.page import parse_page

from conftest import html_page

HOME = "https://www.acme.test/"


def choose(body, home=HOME):
    page = parse_page(home, html_page(body), Config())
    return [(c.topic, c.url) for c in select_links(page, home)]


def test_one_page_per_topic_in_priority_order():
    body = ("<a href='/contact'>Contact</a><a href='/customers'>Customers</a><a href='/about'>About</a>"
            "<a href='/pricing'>Pricing</a><a href='/integrations'>Integrations</a><a href='/features'>Features</a>")
    assert choose(body) == [
        ("product", HOME + "features"),
        ("integrations", HOME + "integrations"),
        ("pricing", HOME + "pricing"),
        ("about", HOME + "about"),
        ("contact", HOME + "contact"),
        ("customers", HOME + "customers"),
    ]


def test_link_text_counts_when_the_path_says_nothing():
    assert choose("<a href='/p/42'>Pricing</a><a href='/c/7'>Our company</a>") == [
        ("pricing", HOME + "p/42"), ("about", HOME + "c/7")]


def test_path_match_beats_text_match_and_shallow_beats_deep():
    body = ("<a href='/blog-free/why-pricing-matters'>Pricing thoughts</a>"
            "<a href='/pricing'>Plans</a><a href='/product/pricing/enterprise'>Enterprise pricing</a>")
    assert choose(body)[0] == ("pricing", HOME + "pricing")


def test_second_choices_follow_the_first_round():
    body = ("<a href='/features'>Features</a><a href='/platform'>Platform</a><a href='/pricing'>Pricing</a>")
    assert choose(body) == [("product", HOME + "features"), ("pricing", HOME + "pricing"),
                            ("product", HOME + "platform")]


def test_offsite_excluded_and_non_page_links_are_dropped():
    body = ("<a href='https://other.test/pricing'>Pricing</a><a href='/blog/pricing'>Pricing post</a>"
            "<a href='/login'>Product login</a><a href='/pricing.pdf'>Pricing PDF</a>"
            "<a href='#pricing'>Pricing</a><a href='/'>Product home</a>"
            "<a href='/legal/terms'>Company terms</a>")
    assert choose(body) == []


def test_duplicates_collapse_and_query_and_fragment_are_ignored_for_identity():
    body = "<a href='/pricing'>Pricing</a><a href='/pricing/'>Plans</a><a href='/pricing#faq'>Pricing FAQ</a>"
    assert choose(body) == [("pricing", HOME + "pricing")]


def test_www_and_bare_host_are_the_same_site():
    assert same_site("https://acme.test/pricing", "https://www.acme.test/")
    assert same_site("http://www.acme.test/x", "https://acme.test/")
    assert not same_site("https://app.acme.test/", "https://www.acme.test/")
    assert not same_site("http://127.0.0.1:8001/", "http://127.0.0.1:8002/")


def test_unrelated_links_are_not_selected():
    assert choose("<a href='/team-photos'>Gallery</a><a href='/x'>Read more</a>") == []
