"""HTML parsing: visible text, head data, links, tables, JavaScript shells."""

import pytest

from agent_scout.config import Config
from agent_scout.page import parse_page, split_sentences

from conftest import html_page

CFG = Config()


def parse(body, head="", title="T", url="http://site.test/"):
    return parse_page(url, html_page(body, title=title, head=head), CFG)


def texts(page, method=None):
    return [s.text for s in page.snippets if method is None or s.method == method]


def test_head_data():
    page = parse("<p>x</p>", title="  My   Title ", head=(
        '<meta name="description" content=" An agent   for email. ">'
        '<meta property="og:description" content="OG text">'
        '<meta name="Description" content="ignored duplicate">'))
    assert page.title == "My Title"
    assert page.meta["description"] == "An agent for email."
    assert page.meta["og:description"] == "OG text"


def test_script_style_noscript_and_comments_are_not_visible_text():
    page = parse("<p>Seen.</p><script>var hidden = 'multi-agent';</script><style>.x{}</style>"
                 "<noscript>Enable JavaScript.</noscript><!-- comment --><template><p>tpl</p></template>")
    joined = " ".join(texts(page))
    assert "Seen." in joined
    for hidden in ("multi-agent", "Enable JavaScript", "comment", "tpl", ".x{}"):
        assert hidden not in joined


def test_headings_sentences_and_zones():
    page = parse("<nav><a href='/pricing'>Pricing</a></nav>"
                 "<main><h1>Big claim</h1><p>First sentence. Second one here! Third?</p></main>"
                 "<footer><p>Footer words here.</p></footer>")
    assert texts(page, "heading") == ["Big claim"]
    assert texts(page, "sentence") == ["First sentence.", "Second one here!", "Third?", "Footer words here."]
    zones = {s.text: s.zone for s in page.snippets}
    assert zones["Pricing"] == "nav" and zones["Footer words here."] == "footer" and zones["Big claim"] == "main"
    assert [s.method for s in page.snippets if s.text == "Pricing"] == ["link"]


def test_inline_markup_stays_in_one_sentence_and_whitespace_collapses():
    page = parse("<p>It <strong>sends</strong>\n   emails <a href='/x'>automatically</a>.</p>")
    assert texts(page, "sentence") == ["It sends emails automatically."]


def test_text_next_to_block_children_is_kept():
    page = parse("<div>Loose text here. <p>Para text.</p> Trailing text.</div>")
    assert texts(page, "sentence") == ["Loose text here.", "Para text.", "Trailing text."]


def test_split_sentences_keeps_abbreviations_and_prices_together():
    assert split_sentences("Plans start at $49.50 per month. Northwind Labs B.V. is small.") == [
        "Plans start at $49.50 per month.", "Northwind Labs B.V. is small."]


def test_links_are_absolute_with_text_or_image_alt():
    page = parse("<a href='/pricing#top'>See  pricing</a><a href='https://other.test/x'><img alt='Other logo' src='o.png'></a>"
                 "<a href='mailto:a@b.test'>Mail</a><a>no href</a>")
    assert [(link.url, link.text) for link in page.links] == [
        ("http://site.test/pricing", "See pricing"),
        ("https://other.test/x", "Other logo"),
    ]


def test_table_rows_become_table_snippets():
    page = parse("<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Free</td><td>$0</td></tr></table>")
    assert page.tables == [[["Plan", "Price"], ["Free", "$0"]]]
    assert texts(page, "table") == ["Plan | Price", "Free | $0"]


def test_address_element_lines_are_joined_with_commas():
    page = parse("<footer><address>Quill Ltd<br>12 Harbour Lane<br>Bristol BS1 4XY<br>United Kingdom</address></footer>")
    assert page.addresses == ["Quill Ltd, 12 Harbour Lane, Bristol BS1 4XY, United Kingdom"]


def test_json_ld_objects_are_flattened_and_bad_json_is_skipped(events):
    head = ('<script type="application/ld+json">{"@graph": [{"@type": "Organization", "name": "A", '
            '"address": {"@type": "PostalAddress", "addressLocality": "Rotterdam"}}, {"@type": "WebSite"}]}</script>'
            '<script type="application/ld+json">{not json}</script>')
    page = parse("<p>x</p>", head=head)
    types = [obj.get("@type") for obj in page.json_ld]
    assert types == ["Organization", "PostalAddress", "WebSite"]
    skipped = [e for e in events() if e["error_type"] == "json_ld_invalid"]
    assert len(skipped) == 1


def test_images_record_alt_and_integration_context():
    page = parse("<main><h2>Hero</h2><img alt='Team photo' src='t.jpg'>"
                 "<section><h2>Integrations</h2><ul><li><img alt='Slack logo' src='s.svg'></li></ul></section>"
                 "<div class='logo-cloud'><img alt='Acme' src='a.svg'></div></main>")
    context = {image.alt: image.in_integration_section for image in page.images}
    assert context == {"Team photo": False, "Slack logo": True, "Acme": False}


def test_integration_heading_without_wrapper_covers_following_siblings():
    page = parse("<main><h2>Works with your stack</h2><p><img alt='HubSpot' src='h.svg'></p>"
                 "<h2>Pricing</h2><p><img alt='Visa' src='v.svg'></p></main>")
    context = {image.alt: image.in_integration_section for image in page.images}
    assert context == {"HubSpot": True, "Visa": False}


SHELL_SCRIPT = "<script>" + "window.app = function(){ return 'x'; };" * 100 + "</script>"


@pytest.mark.parametrize("body, expected", [
    ("<div id='root'></div>" + SHELL_SCRIPT, True),                        # empty root + big inline script
    ("<div id='app'>Loading...</div><script src='/bundle.js'></script>", True),   # external bundle
    ("<p>" + "Plenty of server-rendered words. " * 10 + "</p>" + SHELL_SCRIPT, False),
    ("<p>Coming soon.</p>", False),                                         # tiny, but no scripts
])
def test_needs_rendering(body, expected):
    assert parse(body).needs_rendering is expected


def test_visible_chars_counts_text_only():
    page = parse("<p>12345</p><script>var x = 'not counted';</script>")
    assert page.visible_chars == 5


def test_malformed_link_targets_are_skipped_not_fatal(events):
    page = parse("<a href='http://[broken/'>Broken</a><a href='http://host:notaport/x'>Bad port</a>"
                 "<a href='/fine'>Fine</a>")
    assert [link.url for link in page.links] == ["http://site.test/fine"]
    assert [e["error_type"] for e in events() if e["event"] == "skip"] == ["bad_link", "bad_link"]


def test_json_ld_with_unusual_type_values_does_not_break_extraction():
    from agent_scout import extract
    head = ('<script type="application/ld+json">[{"@type": {"@id": "x"}, "description": "odd", "address": 5, "offers": "none"},'
            '{"@type": ["Organization", {"a": 1}], "description": "An organisation.", "address": {"addressCountry": 7}}]</script>')
    page = parse("<p>" + "Words on the page. " * 20 + "</p>", head=head)
    fields = extract.extract_fields([page], "Acme", CFG)
    assert fields["one_liner"].value == "An organisation."
    assert fields["hq_location"].value == "unknown" and fields["pricing"].value == "unknown"
