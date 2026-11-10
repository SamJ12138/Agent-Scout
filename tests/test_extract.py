"""Each rule-based extractor, on small pages written for the test."""

import pytest

from agent_scout import extract
from agent_scout.config import Config
from agent_scout.model import UNKNOWN
from agent_scout.page import parse_page

from conftest import html_page

CFG = Config()
FILLER = "<p>" + "Ordinary words that say nothing in particular. " * 6 + "</p>"


def page(body, head="", title="Acme", url="https://acme.test/", topic="home"):
    parsed = parse_page(url, html_page(body + FILLER, title=title, head=head), CFG)
    parsed.topic = topic
    return parsed


def meta(text):
    return f'<meta name="description" content="{text}">'


# ------------------------------------------------------------------ one_liner
def test_one_liner_prefers_meta_description():
    result = extract.extract_one_liner([page("<h1>Hero</h1><p>Sub.</p>", head=meta("An agent for ads.") +
                                             '<meta property="og:description" content="OG">')])
    assert result.value == "An agent for ads."
    assert [(e.method, e.quote, e.url) for e in result.evidence] == [("meta", "An agent for ads.", "https://acme.test/")]


def test_one_liner_falls_back_to_og_then_json_ld_then_hero():
    og = extract.extract_one_liner([page("<h1>H</h1>", head='<meta property="og:description" content="OG text">')])
    assert (og.value, og.evidence[0].method) == ("OG text", "meta")
    ld = extract.extract_one_liner([page("<h1>H</h1>", head='<script type="application/ld+json">'
                                         '{"@type": "SoftwareApplication", "description": "LD text"}</script>')])
    assert (ld.value, ld.evidence[0].method) == ("LD text", "json-ld")
    hero = extract.extract_one_liner([page("<h1>Ads that run themselves</h1><p>Acme launches campaigns. More text.</p>")])
    assert hero.value == "Ads that run themselves: Acme launches campaigns."
    assert [e.method for e in hero.evidence] == ["heading", "sentence"]


def test_one_liner_unknown_without_any_description():
    assert extract.extract_one_liner([page("<p>Just words.</p>")]).value == UNKNOWN


def test_one_liner_only_reads_the_homepage():
    pages = [page("<p>x</p>"), page("<p>y</p>", head=meta("Pricing page text"), url="https://acme.test/pricing")]
    assert extract.extract_one_liner(pages).value == UNKNOWN


# ------------------------------------------------------------------ vocabulary fields
def test_category_needs_a_heading_or_meta_or_two_sentences():
    once = extract.extract_vocab([page("<p>We also touch on SEO sometimes.</p>")], "categories")
    assert once.value == UNKNOWN
    heading = extract.extract_vocab([page("<h2>SEO that works</h2>")], "categories")
    assert heading.value == ["seo"] and heading.evidence[0].method == "heading"
    twice = extract.extract_vocab([page("<p>SEO audits weekly. Better SEO for all.</p>")], "categories")
    assert twice.value == ["seo"] and twice.evidence[0].method == "sentence"
    by_meta = extract.extract_vocab([page("<p>x</p>", head=meta("Email marketing on autopilot"))], "categories")
    assert by_meta.value == ["email marketing"] and by_meta.evidence[0].method == "meta"


def test_same_sentence_on_two_pages_counts_once():
    pages = [page("<p>We also touch on SEO sometimes.</p>"),
             page("<p>We also touch on SEO sometimes.</p>", url="https://acme.test/about")]
    assert extract.extract_vocab(pages, "categories").value == UNKNOWN


def test_values_come_out_in_vocabulary_order_each_with_its_own_evidence():
    result = extract.extract_vocab([page("<p>Built for agencies. Loved by marketers.</p>")], "target_user")
    assert result.value == ["marketers", "agencies"]
    assert {e.item: e.quote for e in result.evidence} == {"marketers": "Loved by marketers.",
                                                           "agencies": "Built for agencies."}


def test_negated_nav_footer_table_and_integration_text_are_ignored():
    body = ("<nav><a href='/a'>For agencies</a></nav>"
            "<p>This is not for developers.</p>"
            "<table><tr><td>Enterprise</td><td>For enterprise teams</td></tr></table>"
            "<section><h2>Integrations</h2><p>Works with tools for sales teams.</p></section>"
            "<footer><p>Resources for creators.</p></footer>")
    assert extract.extract_vocab([page(body)], "target_user").value == UNKNOWN


def test_integrations_page_does_not_feed_categories_or_tasks():
    pages = [page("<p>x</p>"), page("<h1>Google Ads</h1><h2>Meta Ads</h2><p>Shopify and a CRM.</p>",
                                     url="https://acme.test/integrations", topic="integrations")]
    assert extract.extract_vocab(pages, "categories").value == UNKNOWN
    assert extract.extract_vocab(pages, "tasks").value == UNKNOWN


def test_tasks_are_reported_when_stated_once():
    result = extract.extract_vocab([page("<p>It writes product descriptions and schedules posts.</p>")], "tasks")
    assert result.value == ["write copy", "schedule social posts"]


# ------------------------------------------------------------------ can_execute
@pytest.mark.parametrize("sentence, expected", [
    ("It sends each email campaign automatically.", True),
    ("Campaigns are launched on your behalf.", True),
    ("AI agents that plan, launch and optimize campaigns.", True),
    ("The agent updates your CRM after every call.", True),
    ("Send campaigns faster with our editor.", UNKNOWN),                 # the user sends
    ("Our agents help you launch campaigns.", UNKNOWN),                  # the user launches
    ("The agent drafts posts and emails for you to review.", UNKNOWN),
    ("It writes posts automatically.", UNKNOWN),                         # writing is not acting in a channel
    ("Automatically generated insights every week.", UNKNOWN),
    ("It only drafts; you press send.", False),
    ("The assistant never sends anything without you.", UNKNOWN),    # a condition, not "only drafts"
    ("The assistant never sends anything.", False),
    ("Unlike tools that publish posts automatically, we only suggest.", UNKNOWN),
])
def test_can_execute_three_values(sentence, expected):
    result = extract.extract_can_execute([page(f"<p>{sentence}</p>")])
    assert result.value == expected
    if expected != UNKNOWN:
        assert result.evidence[0].quote == sentence


def test_can_execute_conflict_is_unknown(events):
    body = "<p>It sends each email campaign automatically.</p><p>The tool only drafts.</p>"
    assert extract.extract_can_execute([page(body)]).value == UNKNOWN
    assert any(e["error_type"] == "conflicting_statements" for e in events())


# ------------------------------------------------------------------ multi_agent
def test_multi_agent_is_true_or_unknown_never_false():
    assert extract.extract_multi_agent([page("<p>A team of AI agents runs it.</p>")]).value is True
    assert extract.extract_multi_agent([page("<p>One assistant does it all.</p>")]).value == UNKNOWN
    assert extract.extract_multi_agent([page("<p>This is not a multi-agent system.</p>")]).value == UNKNOWN


# ------------------------------------------------------------------ integrations
def integrations(pages):
    return extract.extract_integrations(pages, "Acme", 25)


def test_integration_page_logos_links_and_known_names():
    body = ("<header><img alt='Acme logo' src='a.svg'></header>"
            "<h1>Integrations</h1><ul>"
            "<li><img alt='HubSpot logo' src='h.svg'></li>"
            "<li><img alt='Fernleaf CRM logo' src='f.svg'></li>"
            "<li><a href='/integrations/slack'>Slack</a></li>"
            "<li><h3>Google Analytics 4</h3><p>Sync conversions.</p></li>"
            "<li><img alt='Decorative arrow' src='x.svg'></li>"
            "<li><h3>Popular</h3></li></ul>"
            "<a href='/contact'>Request an integration</a>")
    result = integrations([page(body, url="https://acme.test/integrations", topic="integrations")])
    assert result.value == ["HubSpot", "Fernleaf CRM", "Slack", "Google Analytics 4"]     # as the site writes it
    assert {e.item: (e.method, e.quote) for e in result.evidence} == {
        "HubSpot": ("link", "HubSpot logo"), "Fernleaf CRM": ("link", "Fernleaf CRM logo"),
        "Slack": ("link", "Slack"), "Google Analytics 4": ("heading", "Google Analytics 4")}


def test_integration_section_on_the_homepage_and_customer_logos_elsewhere():
    body = ("<div class='customers'><img alt='Stripe logo' src='s.svg'></div>"
            "<section><h2>Works with your stack</h2><img alt='Shopify' src='s.svg'><img alt='Team photo' src='t.jpg'></section>")
    assert integrations([page(body)]).value == ["Shopify"]


def test_integrations_named_in_a_sentence():
    result = integrations([page("<p>Acme integrates with Instagram, LinkedIn, TikTok and Slack.</p>"
                                "<p>It works with your existing tools. Connect to anything.</p>")])
    assert result.value == ["Instagram", "LinkedIn", "TikTok", "Slack"]
    assert all(e.method == "sentence" for e in result.evidence)


def test_integration_sentence_keeps_unknown_capitalised_names_and_stops_at_prose():
    result = integrations([page("<p>Syncs with Fernleaf CRM, Zapier and Monday.com to keep data fresh.</p>")])
    assert result.value == ["Fernleaf CRM", "Zapier", "Monday.com"]


def test_integrations_limit_and_dedupe():
    names = list(extract.KNOWN_INTEGRATIONS)[:30]
    body = "<h1>Integrations</h1>" + "".join(f"<img alt='{n} logo' src='x'><img alt='{n}' src='y'>" for n in names)
    result = extract.extract_integrations([page(body, topic="integrations")], "Acme", 25)
    assert len(result.value) == 25 and len(set(result.value)) == 25


def test_no_integrations_is_unknown():
    assert integrations([page("<p>Nothing here.</p>")]).value == UNKNOWN


# ------------------------------------------------------------------ pricing
def pricing(pages):
    return extract.extract_pricing(pages).value


def pricing_page(body):
    return page(body, url="https://acme.test/pricing", topic="pricing")


def test_pricing_table_with_free_row():
    body = ("<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Free</td><td>$0</td></tr>"
            "<tr><td>Pro</td><td>$49/month</td></tr><tr><td>Max</td><td>$199/month</td></tr></table>"
            "<p>Save $120 per year when you pay yearly.</p>")
    result = extract.extract_pricing([pricing_page(body)])
    assert result.value == {"free_tier": True, "starting_price": "$49/month"}
    by_item = {e.item: e for e in result.evidence}
    assert (by_item["starting_price"].method, by_item["starting_price"].quote) == ("table", "Pro | $49/month")
    assert (by_item["free_tier"].method, by_item["free_tier"].quote) == ("table", "Free | $0")


@pytest.mark.parametrize("body, expected", [
    ("<h2>Solo</h2><p>£29 per month</p><h2>Team</h2><p>£79 per month</p>", "£29 per month"),
    ("<p>$99/mo billed monthly or $948/year.</p>", "$99/mo"),
    ("<p>€15 per user per month</p><p>€12/user/month billed yearly</p>", "€12/user/month"),
    ("<p>Plans cost $1,200 a year.</p>", "$1,200 a year"),
    ("<h3>$19</h3><p>per month</p><h3>$49</h3>", "$19"),
    ("<p>Talk to sales for a quote.</p>", UNKNOWN),
    ("<p>Get $50 off your first order and a $10 credit.</p>", UNKNOWN),
])
def test_starting_price_as_written(body, expected):
    value = pricing([pricing_page(body)])
    got = value if value == UNKNOWN else value["starting_price"]
    assert got == expected


def test_price_outside_a_pricing_page_needs_a_cue():
    assert pricing([page("<p>We raised $40 million and customers saved $5 each.</p>")]) == UNKNOWN
    assert pricing([page("<p>Plans start at $29/month.</p>")]) == {"free_tier": UNKNOWN, "starting_price": "$29/month"}


@pytest.mark.parametrize("body, expected", [
    ("<a href='/signup'>Start your free trial</a>", True),
    ("<p>Every plan starts with a 14-day free trial.</p>", True),
    ("<h3>Free</h3><p>For individuals.</p>", True),
    ("<p>There is no free plan.</p>", False),
    ("<p>Feel free to contact us. Shipping is free of charge.</p>", UNKNOWN),
])
def test_free_tier_three_values(body, expected):
    value = pricing([pricing_page(body)])
    got = value if value == UNKNOWN else value["free_tier"]
    assert got == expected


def test_pricing_from_json_ld_offers_when_no_price_is_visible():
    head = ('<script type="application/ld+json">{"@type": "SoftwareApplication", "offers": '
            '[{"@type": "Offer", "price": "0", "priceCurrency": "USD"}, {"@type": "Offer", "price": "29.00", "priceCurrency": "USD"}]}</script>')
    result = extract.extract_pricing([page("<p>x</p>", head=head)])
    assert result.value == {"free_tier": True, "starting_price": "29.00 USD"}
    assert {e.method for e in result.evidence} == {"json-ld"}


# ------------------------------------------------------------------ hq_location
def hq(pages):
    return extract.extract_hq(pages)


def test_hq_from_json_ld_address_with_iso_country_code():
    head = ('<script type="application/ld+json">{"@type": "Organization", "address": {"@type": "PostalAddress", '
            '"streetAddress": "Wilhelminakade 900", "addressLocality": "Rotterdam", "addressCountry": "NL"}}</script>')
    result = hq([page("<p>x</p>", head=head)])
    assert result.value == {"city": "Rotterdam", "country": "Netherlands"}
    assert result.evidence[0].method == "json-ld" and "Rotterdam" in result.evidence[0].quote


def test_hq_from_json_ld_region_alone_does_not_state_the_country():
    def with_address(fields):
        return page("<p>x</p>", head='<script type="application/ld+json">{"@type": "Organization", "address": {'
                    + fields + '}}</script>')
    bare = hq([with_address('"addressLocality": "Perth", "addressRegion": "WA"')])
    assert bare.value == {"city": "Perth", "country": UNKNOWN}
    zipped = hq([with_address('"addressLocality": "Seattle", "addressRegion": "WA", "postalCode": "98101"')])
    assert zipped.value == {"city": "Seattle", "country": "United States"}


def test_hq_from_json_ld_country_object_and_us_region():
    head = ('<script type="application/ld+json">{"@type": "Corporation", "address": {"addressLocality": "Austin", '
            '"addressRegion": "TX", "addressCountry": {"@type": "Country", "name": "USA"}}}</script>')
    assert hq([page("<p>x</p>", head=head)]).value == {"city": "Austin", "country": "United States"}


def test_hq_from_address_element():
    result = hq([page("<footer><address>Quill Ltd<br>12 Harbour Lane<br>Bristol BS1 4XY<br>United Kingdom</address></footer>")])
    assert result.value == {"city": "Bristol", "country": "United Kingdom"}
    assert result.evidence[0].quote == "Quill Ltd, 12 Harbour Lane, Bristol BS1 4XY, United Kingdom"


@pytest.mark.parametrize("sentence, expected", [
    ("Acme Inc. is headquartered in Toronto, Canada.", {"city": "Toronto", "country": "Canada"}),
    ("We are based in San Francisco, CA and hiring.", {"city": "San Francisco", "country": UNKNOWN}),
    ("We are based in San Francisco, California and hiring.", {"city": "San Francisco", "country": "United States"}),
    ("Headquarters: 500 Howard St, San Francisco, CA 94105", {"city": "San Francisco", "country": "United States"}),
    ("Headquarters: Tel Aviv, Israel", {"city": "Tel Aviv", "country": "Israel"}),
    ("Based in Berlin.", {"city": "Berlin", "country": UNKNOWN}),
    ("We are based in Germany.", {"city": UNKNOWN, "country": "Germany"}),
    ("Our team is based in the cloud.", UNKNOWN),
    ("A remote team based in Europe.", UNKNOWN),
    ("Customers in Toronto, Canada love us.", UNKNOWN),          # no headquarters cue
])
def test_hq_from_a_sentence(sentence, expected):
    assert hq([page(f"<p>{sentence}</p>")]).value == expected


def test_hq_from_footer_address_line_without_address_element():
    result = hq([page("<footer><p>© 2026 Acme Inc. 500 Howard St, San Francisco, CA 94105</p></footer>")])
    assert result.value == {"city": "San Francisco", "country": "United States"}


def test_hq_unknown():
    assert hq([page("<p>We love our customers.</p>")]).value == UNKNOWN


# ------------------------------------------------------------------ whole site
def test_needs_rendering_page_contributes_head_data_only():
    shell = parse_page("https://acme.test/", html_page(
        "<div id='root'></div><script>" + "var copy = 'multi-agent team that sends campaigns automatically';" * 60 + "</script>",
        head=meta("Acme sends email campaigns automatically for agencies.")), CFG)
    assert shell.needs_rendering
    fields = extract.extract_fields([shell], "Acme", CFG)
    assert fields["one_liner"].value == "Acme sends email campaigns automatically for agencies."
    for name in ("categories", "target_user", "tasks", "can_execute", "multi_agent", "integrations"):
        assert fields[name].value == UNKNOWN, name


def test_no_pages_means_every_field_unknown():
    fields = extract.extract_fields([], "Acme", CFG)
    assert all(result.value == UNKNOWN and result.evidence == [] for result in fields.values())


def test_every_extracted_field_is_logged_with_its_methods(events):
    extract.extract_fields([page("<h2>SEO that works</h2>", head=meta("An SEO agent."))], "Acme", CFG, site="acme")
    done = {e["context"]["field"]: e for e in events() if e["stage"] == "extract" and e["event"] != "start"}
    assert set(done) == set(extract.FIELDS)
    assert done["one_liner"]["event"] == "success" and done["one_liner"]["context"]["methods"] == ["meta"]
    assert done["hq_location"]["event"] == "skip" and done["hq_location"]["error_type"] == "not_stated"
    assert done["categories"]["site"] == "acme"
