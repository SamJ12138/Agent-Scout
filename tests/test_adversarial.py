"""Sentences and pages written to make the extractors say something false.

They come from an independent review of the tool. The rule they enforce: a
field may come out "unknown", but it must not come out as a wrong true, a
wrong false or a list of things the site never claimed. Add to this file
whenever a wrong value is found; never delete from it.
"""

import pytest

from agent_scout import extract
from agent_scout.config import Config
from agent_scout.geo import parse_place
from agent_scout.model import FIELDS, UNKNOWN
from agent_scout.page import parse_page

from conftest import html_page

CFG = Config()
FILLER = "<p>" + "Ordinary words that say nothing in particular. " * 6 + "</p>"


def page(body, head="", title="Acme", url="https://acme.test/", topic="home", filler=True):
    parsed = parse_page(url, html_page(body + (FILLER if filler else ""), title=title, head=head), CFG)
    parsed.topic = topic
    return parsed


def pricing_page(body):
    return page(body, url="https://acme.test/pricing", topic="pricing")


# ------------------------------------------------------------------ can_execute
@pytest.mark.parametrize("sentence, allowed", [
    # a negated verb with a specific object is not "it only drafts"
    ("Relaywise never sends duplicate emails to a subscriber.", [UNKNOWN]),
    ("Zed does not publish fake reviews.", [UNKNOWN]),
    ("It never posts off-brand content.", [UNKNOWN]),
    # an approval step is not "a human must do the action"
    ("A human must approve the first campaign; after that the agent sends campaigns automatically.", [True, UNKNOWN]),
    ("Our agents never send anything without your approval.", [True, UNKNOWN]),
    ("The assistant never sends anything unless you say so.", [True, UNKNOWN]),
    # the person does the sending
    ("Quillon writes emails for you to send.", [UNKNOWN]),
    ("Drafts are ready so you can publish posts automatically from your own tool.", [UNKNOWN]),
    ("You never send a campaign late again.", [UNKNOWN]),
    # a statement about other products
    ("Other tools send campaigns automatically and hope for the best.", [UNKNOWN]),
    ("Most platforms publish posts automatically without a second look.", [UNKNOWN]),
    # a question or a rhetorical heading asserts nothing
    ("Should an agent send campaigns automatically?", [UNKNOWN]),
    # unambiguous statements still work
    ("Pennabright does not send emails for you.", [False]),
    ("It never sends or publishes anything, and a person on your team posts the final version.", [False]),
    ("The tool only drafts.", [False]),
    ("It sends each email campaign automatically.", [True]),
])
def test_can_execute(sentence, allowed):
    assert extract.extract_can_execute([page(f"<p>{sentence}</p>")]).value in allowed


def test_can_execute_competitor_sentence_followed_by_own_description():
    body = "<p>Other tools send campaigns automatically and hope for the best. Calmpost shows you every message first.</p>"
    assert extract.extract_can_execute([page(body)]).value == UNKNOWN


# ------------------------------------------------------------------ multi_agent
@pytest.mark.parametrize("body", [
    "<h2>Why multi-agent systems fail</h2><p>Most of them collapse under their own complexity. Solowing is one assistant.</p>",
    "<p>We are not a multi-agent system. Brightdesk is a single assistant that answers one question at a time.</p>",
    "<h2>Do you need a team of agents?</h2><p>Probably not.</p>",
    "<p>Other platforms sell a team of AI agents; we sell one that works.</p>",
    "<blockquote><p>Their multi-agent setup replaced three tools for us.</p><cite>A customer</cite></blockquote>",
])
def test_multi_agent_is_not_claimed(body):
    assert extract.extract_multi_agent([page(body)]).value == UNKNOWN


# ------------------------------------------------------------------ integrations
@pytest.mark.parametrize("body", [
    "<h2>Connect to Customers Faster</h2><p>Works with Marketing Teams of any size.</p>",
    "<p>Integrates with Your Brand Guidelines and Every Channel.</p>",
    "<h2>What customers say</h2><blockquote><p>“We connected it to Salesforce and HubSpot in a day, and it works with "
    "Slack out of the box.”</p><cite>Dana Whitlow, Operations lead at Corvid Supply</cite></blockquote>",
    "<div class='testimonial-card'><p>It works with Slack and Notion, which sold us.</p></div>",
])
def test_integrations_are_not_invented(body):
    assert extract.extract_integrations([page(body)], "Acme", 25).value == UNKNOWN


# ------------------------------------------------------------------ vocabulary fields
@pytest.mark.parametrize("body, field", [
    ("<p>Cheaper than an agency. Faster than hiring engineers.</p>", "target_user"),
    ("<p>Like having a team of developers, without the payroll.</p>", "target_user"),
    ("<p>SEO is not something we do. Chatbots are not part of the product either.</p>", "tasks"),
    ("<p>SEO is not something we do. Chatbots are not part of the product either.</p>", "categories"),
    ("<p>Other tools do keyword research and call it a day.</p>", "tasks"),
    ("<blockquote><p>We used to pay $5,000 a month for an agency.</p><cite>Priya N., founder</cite></blockquote>", "target_user"),
    ("<blockquote><p>The SEO reports alone are worth it.</p></blockquote>", "tasks"),
    ("<div id='cookie-banner'><h2>We use analytics cookies</h2><p>Analytics and advertising partners help us.</p></div>", "tasks"),
    ("<div id='cookie-banner'><h2>We use analytics cookies</h2><p>Analytics and advertising partners help us.</p></div>", "categories"),
])
def test_vocabulary_values_are_not_invented(body, field):
    assert extract.extract_vocab([page(body)], field).value == UNKNOWN


# ------------------------------------------------------------------ headquarters
@pytest.mark.parametrize("sentence, expected", [
    ("Our customer Fjordline, based in Berlin, Germany, doubled its sign-ups in a quarter.", UNKNOWN),
    ("We work with agencies headquartered in London, UK.", UNKNOWN),
    ("Zed is headquartered in Tbilisi, Georgia.", {"city": "Tbilisi", "country": UNKNOWN}),
    ("We are a remote team based in Berlin, DE.", {"city": "Berlin", "country": UNKNOWN}),
    ("Headquartered in Toronto, CA.", {"city": "Toronto", "country": UNKNOWN}),
    ("Headquartered in Austin, TX 78701.", {"city": "Austin", "country": "United States"}),
])
def test_hq(sentence, expected):
    assert extract.extract_hq([page(f"<p>{sentence}</p>")]).value == expected


def test_hq_is_not_read_from_a_testimonial():
    body = "<blockquote><p>Our team, based in Oslo, Norway, saved a day a week.</p><cite>Customer</cite></blockquote>"
    assert extract.extract_hq([page(body)]).value == UNKNOWN


@pytest.mark.parametrize("text, expected", [
    ("Berlin, DE", ("Berlin", None)),                 # DE is Germany and Delaware
    ("Toronto, CA", ("Toronto", None)),               # CA is Canada and California
    ("Bengaluru, IN", ("Bengaluru", None)),           # IN is India and Indiana
    ("Tbilisi, Georgia", ("Tbilisi", None)),          # a country and a state
    ("Perth, WA", ("Perth", None)),                   # Western Australia, not Washington
    ("Portland, OR", ("Portland", None)),             # a bare state code states no country
    ("Lyon, FR", ("Lyon", "France")),                 # an ISO country code that is not a state code
    ("Portland, OR 97204", ("Portland", "United States")),
    ("Atlanta, GA 30301", ("Atlanta", "United States")),
    ("Toronto, CA, USA", ("Toronto", "United States")),   # explicit marker: the site said so
    ("San Francisco, California", ("San Francisco", "United States")),
    ("Toronto, Canada", ("Toronto", "Canada")),
])
def test_places_are_never_guessed(text, expected):
    assert parse_place(text) == expected


# ------------------------------------------------------------------ pricing
@pytest.mark.parametrize("body, expected", [
    ("<p>No free trial limits. Use the Starter plan as long as you like.</p>", UNKNOWN),
    ("<p>Setup fee: $0. The Team plan is $99/month.</p><p>Customers earn back $3 for every $1 spent on Ledgerly.</p>",
     {"free_tier": UNKNOWN, "starting_price": "$99/month"}),
    ("<table><tr><td>Onboarding</td><td>$0</td></tr><tr><td>Pro</td><td>$49/month</td></tr></table>",
     {"free_tier": UNKNOWN, "starting_price": "$49/month"}),
    ("<section><h2>Starter</h2><p>$99/month</p></section><section><h2>Scale</h2><p>$299/month</p></section>"
     "<blockquote><p>“We used to pay $40/month for a scheduling tool and $5,000 a month for an agency.”</p>"
     "<cite>Priya N., founder</cite></blockquote>", {"free_tier": UNKNOWN, "starting_price": "$99/month"}),
    ("<p>There is no free plan. Paid plans start at $99 per month.</p>",
     {"free_tier": False, "starting_price": "$99 per month"}),
    ("<p>We do not offer a free plan.</p><p>Team: $30 per user per month. Extra seats are $5.</p>",
     {"free_tier": False, "starting_price": "$30 per user per month"}),
    ("<blockquote><p>The free trial convinced us in a day.</p></blockquote><p>Talk to sales.</p>", UNKNOWN),
])
def test_pricing(body, expected):
    assert extract.extract_pricing([pricing_page(body)]).value == expected


# ------------------------------------------------------------------ navigation is never a statement
NAV_ONLY = """
<header><div class="menu"><ul>
<li><a href="/seo">SEO</a></li><li><a href="/email">Email marketing</a></li><li><a href="/agencies">For agencies</a></li>
<li><a href="/x"><strong>Chatbots</strong> <span>Answer customer questions around the clock</span></a></li>
<li><button>Integrations</button></li><li><a href="/slack">Slack</a></li><li><a href="/hubspot">HubSpot</a></li>
<li><a href="/free">Start free</a></li></ul></div></header>
<nav><a href="/a">Social media scheduling</a> <a href="/b">Multi-agent teams</a> <a href="/c">Plans from $19/month</a></nav>
<footer><a href="/terms">Terms</a> <a href="/privacy">Privacy</a> <p>Free trial available. Based in Oslo, Norway.</p></footer>
"""


def test_a_page_that_is_only_navigation_states_nothing_about_the_product():
    fields = extract.extract_fields([page(NAV_ONLY, filler=False)], "Acme", CFG)
    for name in FIELDS:
        if name == "hq_location":
            continue                     # a footer may state where the company is
        assert fields[name].value == UNKNOWN, (name, fields[name].value)
    assert fields["hq_location"].value == {"city": "Oslo", "country": "Norway"}


@pytest.mark.parametrize("wrapper", [
    "<nav>{}</nav>", "<div role='navigation'>{}</div>", "<div class='site-navbar'>{}</div>",
    "<ul class='main-menu'>{}</ul>", "<div id='breadcrumbs'>{}</div>",
])
def test_navigation_is_recognised_by_tag_role_or_class(wrapper):
    body = wrapper.format("<a href='/a'>Start your free trial</a> <a href='/b'>Plans from $19/month</a>")
    assert extract.extract_pricing([pricing_page(body)]).value == UNKNOWN


def test_a_class_on_the_page_wrapper_does_not_turn_the_whole_page_into_navigation():
    body = "<div class='has-nav menu-open'><main><h1>Acme</h1><p>Every plan starts with a 14-day free trial.</p></main></div>"
    assert extract.extract_pricing([pricing_page(body)]).value == {"free_tier": True, "starting_price": UNKNOWN}


# ------------------------------------------------------------------ one_liner
def test_cookie_banner_is_not_the_one_liner():
    body = ("<h2>We value your privacy</h2><p>We use cookies to improve your experience.</p>"
            "<h1>Zed runs your ads</h1><p>Zed is an ads agent.</p>")
    assert extract.extract_one_liner([page(body)]).value == "Zed runs your ads: Zed is an ads agent."


def test_consent_container_and_testimonial_are_not_the_one_liner():
    body = ("<div class='cookie-consent'><h2>Cookies</h2><p>Accept all cookies to continue.</p></div>"
            "<blockquote><h3>Best tool ever</h3><p>It changed our week.</p></blockquote>")
    assert extract.extract_one_liner([page(body)]).value == UNKNOWN


# ====================================================================== found on real sites (corpus run 1)
# Each case below is a sentence shape seen in the first run on real websites,
# rewritten with invented names. The rule it pins must hold on any site.

# ------------------------------------------------------------------ an infinitive is a purpose, not an act
@pytest.mark.parametrize("sentence", [
    "Instant Ads scans your webpage to produce high-performing, ready-to-launch advertisements, automatically "
    "tailored to engage your ideal audience.",
    "Download ready-to-publish posts, generated automatically for your brand.",
    "Ads that are ready to launch are created automatically.",
    "Everything you need to send campaigns automatically.",
])
def test_an_infinitive_or_ready_to_compound_does_not_state_that_the_product_acts(sentence):
    assert extract.extract_can_execute([page(f"<p>{sentence}</p>")]).value == UNKNOWN


# ------------------------------------------------------------------ free plan or trial: denials
@pytest.mark.parametrize("sentence, expected", [
    ("We're not able to offer free trials at this time.", False),
    ("We don't have a free plan yet.", False),
    ("Zed no longer offers a free tier.", False),
    ("Free trials are not available.", False),
    ("There is no free plan.", False),
    ("No free trial limits.", UNKNOWN),
    ("Free trials are available on every plan.", True),
])
def test_free_tier_denials_need_a_verb_of_offering(sentence, expected):
    value = extract.extract_pricing([pricing_page(f"<p>{sentence}</p>")]).value
    assert (value if value == UNKNOWN else value["free_tier"]) == expected


@pytest.mark.parametrize("sentence", [
    "You do not need a credit card for the free trial.",
    "No credit card is required for the free plan.",
])
def test_a_negation_about_something_else_is_not_a_denial_of_the_free_tier(sentence):
    value = extract.extract_pricing([pricing_page(f"<p>{sentence}</p>")]).value
    assert (value if value == UNKNOWN else value["free_tier"]) in (True, UNKNOWN)


# ------------------------------------------------------------------ integrations: as written, known names first
def test_integration_names_are_reported_as_the_site_writes_them():
    body = ("<h1>Integrations</h1><img alt='Google BigQuery logo' src='a'><img alt='bigcommerce logo' src='b'>"
            "<h3>Google Analytics 4</h3><img alt='BigQuery' src='c'>")
    result = extract.extract_integrations([page(body, topic="integrations")], "Acme", 25)
    assert result.value == ["Google BigQuery", "BigCommerce", "Google Analytics 4"]     # one entry per product


def test_a_long_alphabetical_directory_does_not_crowd_out_the_names_a_reader_knows():
    obscure = "".join(f"<img alt='Aardvark{n} logo' src='x{n}'>" for n in range(40))
    body = "<h1>Integrations</h1>" + obscure + "<img alt='HubSpot logo' src='h'><img alt='Slack logo' src='s'>"
    result = extract.extract_integrations([page(body, topic="integrations")], "Acme", 25)
    assert len(result.value) == 25
    assert result.value[-2:] == ["HubSpot", "Slack"]                 # kept, in page order
    assert result.value[:23] == [f"Aardvark{n}" for n in range(23)]


# ------------------------------------------------------------------ prices (corpus run 1)
@pytest.mark.parametrize("body, expected", [
    # a spend slider, not prices: "$2.5K" must not be read as "$2"
    ("<p>Less than $1K $1K - $2.5K $2.5K - $5K $5K - $10K $10K - $20K $30K+</p>", UNKNOWN),
    ("<p>Trusted with $1.5M of monthly ad spend.</p>", UNKNOWN),
    # the currency after the amount
    ("<table><tr><td>Essential 42€/ month billed annually</td><td>Pro 84€/ month per user</td></tr></table>", "42€/ month"),
    ("<p>Starter 29 € per month</p><p>Team 99 € per month</p>", "29 € per month"),
    ("<p>Team 49 EUR/month</p>", "49 EUR/month"),
    ("<p>Jahresplan 1.299,00 € / year</p><p>Monatsplan 129,00 € / month</p>", "129,00 € / month"),
    # an add-on is not the price of a plan
    ("<p>Core $19 /month</p><p>Extra Brand ($5/month)</p>", "$19 /month"),
    ("<p>Pro $49/month</p><p>Each additional seat costs $9/month.</p>", "$49/month"),
    ("<p>Add-on: Tracking Pro $49/mo</p>", UNKNOWN),
    # the amount and its period in neighbouring elements
    ("<div><h3>$149</h3><p>per month</p></div><div><h3>$299</h3><p>per month</p></div>", "$149 per month"),
    ("<div><span class='block'><p>$15</p></span><p>/mo</p></div>", "$15 /mo"),
    ("<h3>$149</h3><p>Everything you need to rank.</p>", "$149"),
    # a struck-through list price glued to the real one
    ("<p>$25$1/month</p>", "$1/month"),
])
def test_starting_price_shapes_seen_on_real_sites(body, expected):
    value = extract.extract_pricing([pricing_page(body)]).value
    assert (value if value == UNKNOWN else value["starting_price"]) == expected


def test_a_pricing_section_on_the_homepage_is_read_like_a_pricing_page():
    body = ("<section><h2>Trusted by teams that raised $40 million</h2><p>Customers saved $5 each.</p></section>"
            "<section><h2>Plans and pricing</h2><div><h3>Starter</h3><p>$29</p></div><div><h3>Pro</h3><p>$99</p></div></section>"
            "<section><h2>FAQ</h2><p>Refunds of $10 are possible.</p></section>")
    result = extract.extract_pricing([page(body)])
    assert result.value == {"free_tier": UNKNOWN, "starting_price": "$29"}
    assert result.evidence[0].quote == "$29"


def test_the_period_is_quoted_with_the_price_it_was_joined_to():
    body = "<div><h3>$149</h3><p>per month</p></div>"
    result = extract.extract_pricing([pricing_page(body)])
    assert [e.quote for e in result.evidence] == ["$149 per month"]


# ------------------------------------------------------------------ vocabulary extras (corpus run 1)
def _vocab(body, field):
    return extract.extract_vocab([page(body)], field).value


@pytest.mark.parametrize("body, field, unwanted", [
    # a question asserts nothing (FAQ headings)
    ("<h3>Is Zedly a chatbot?</h3>", "tasks", "customer chat"),
    ("<h3>Is Zedly a chatbot?</h3><h3>Is this a customer service chatbot?</h3>", "categories", "customer support"),
    ("<h3>Do I need developers to get started?</h3>", "target_user", "developers"),
    ("<p>Do newsletters even work these days?</p>", "tasks", "send email campaigns"),
    # a clause about other products, with a word between the quantifier and the noun
    ("<p>Most SEO tools give you dashboards, warnings, keyword lists, and recommendations.</p>", "tasks", "analytics reporting"),
    ("<p>Traditional marketing platforms send newsletters on a fixed schedule.</p>", "tasks", "send email campaigns"),
    ("<p>Many other AI assistants stop at keyword research.</p>", "tasks", "seo optimization"),
    # "personality" is not personalisation
    ("<p>Values, personality, and motivation as the foundation of every response.</p>", "tasks", "personalization"),
    # the vendor's own staff are not the audience
    ("<p>Contact Zedly's sales team to customise the Business plan.</p>", "target_user", "sales teams"),
    ("<p>Talk to our sales team about volume pricing.</p>", "target_user", "sales teams"),
    ("<p>Today an international team of engineers and researchers works across three continents.</p>", "target_user", "developers"),
    ("<p>A team of marketers and linguists built the technology.</p>", "target_user", "marketers"),
    # one firm in a story is not an audience; sellers on a marketplace are not sales teams
    ("<p>Brightside Media, an Orlando-based digital marketing agency, wrote forty posts in a month.</p>", "target_user", "agencies"),
    ("<p>This enabled the agency to stay ahead of the competition.</p>", "target_user", "agencies"),
    ("<p>Join thousands of sellers who rely on Zedly every day.</p>", "target_user", "sales teams"),
    # who it is for, or what it connects to, is not what kind of work it does
    ("<h2>Built for E-Commerce Brands</h2>", "categories", "ecommerce"),
    ("<h2>Connect your Shopify store</h2><p>These include ad accounts and Shopify stores.</p>", "categories", "ecommerce"),
    # a kind of content it writes is not a channel it manages or schedules
    ("<p>Zedly handles articles, emails, ads, social posts, and more.</p>", "tasks", "schedule social posts"),
    ("<p>Zedly handles articles, emails, ads, social posts, and more.</p><p>Write social posts in seconds.</p>", "categories", "social media"),
    # naming an ad platform, or ad spend as data, does not say the product manages ads
    ("<p>Trained on patterns learned from $35B in ad spend data.</p>", "tasks", "manage ads"),
    ("<h3>Facebook Ads</h3><p>Square and story formats.</p>", "tasks", "manage ads"),
    ("<p>Writes your Facebook ads.</p>", "tasks", "manage ads"),
    # the vendor's support channel is not a product feature
    ("<p>To request a refund, reach out via live chat or email.</p>", "tasks", "customer chat"),
    ("<p>Free training + live chat support</p>", "tasks", "customer chat"),
])
def test_extras_seen_on_real_sites_are_not_reported(body, field, unwanted):
    value = _vocab(body, field)
    assert value == UNKNOWN or unwanted not in value, value


@pytest.mark.parametrize("body, field, wanted", [
    ("<p>Built for agencies and in-house teams.</p>", "target_user", "agencies"),
    ("<p>Run your agency on one platform.</p>", "target_user", "agencies"),
    ("<p>Our platform helps marketers ship faster.</p>", "target_user", "marketers"),
    ("<h2>Built for E-Commerce Brands</h2>", "target_user", "ecommerce brands"),
    ("<h2>Ecommerce marketing on autopilot</h2>", "categories", "ecommerce"),
    ("<p>Runs your Facebook ads autonomously.</p>", "tasks", "manage ads"),
    ("<p>Builds and optimizes Google Ads.</p>", "tasks", "manage ads"),
    ("<p>Agentic campaign management for ad ROI.</p>", "tasks", "manage ads"),
    ("<h3>Social posts and autoposting</h3>", "tasks", "schedule social posts"),
    ("<p>Personalised subject lines for every reader.</p>", "tasks", "personalization"),
    ("<p>A chatbot that answers every visitor.</p>", "tasks", "customer chat"),
])
def test_the_tightened_rules_still_find_plain_statements(body, field, wanted):
    value = _vocab(body, field)
    assert value != UNKNOWN and wanted in value, value


# ------------------------------------------------------------------ headquarters (corpus run 1)
@pytest.mark.parametrize("body, expected", [
    # "customer success specialists" far before the cue is not "our customer X, based in ..."
    ("<p>Today, an international team of engineers and customer success specialists works across multiple "
     "continents, with headquarters in Hamburg.</p>", {"city": "Hamburg", "country": UNKNOWN}),
    ("<p>Our customer Fjordline, based in Berlin, Germany, doubled its sign-ups.</p>", UNKNOWN),
    ("<p>We work with agencies headquartered in London, UK.</p>", UNKNOWN),
    # a footer address without commas: postcode, city, country
    ("<footer><p>Zedly ApS Diplomvej 381 2800 Kongens Lyngby Denmark</p></footer>",
     {"city": "Kongens Lyngby", "country": "Denmark"}),
    ("<footer><div>Zedly ApS<br>Diplomvej 381<br>2800 Kongens Lyngby<br>Denmark</div></footer>",
     {"city": "Kongens Lyngby", "country": "Denmark"}),
    # the same address, one element per line
    ("<footer><p>Zedly ApS</p><p>Diplomvej 381</p><p>2800 Kongens Lyngby</p><p>Denmark</p></footer>",
     {"city": "Kongens Lyngby", "country": "Denmark"}),
    # numbers that are not an address
    ("<footer><p>Copyright 2026 Zedly Denmark</p></footer>", UNKNOWN),
    ("<footer><p>Copyright 2026 Zedly, Denmark</p></footer>", UNKNOWN),
    ("<footer><p>Copyright 2026 Zedly</p><p>Denmark</p></footer>", UNKNOWN),
    ("<footer><p>Rated 4.8 by 2000 Happy Teams Worldwide</p></footer>", UNKNOWN),
])
def test_hq_shapes_seen_on_real_sites(body, expected):
    assert extract.extract_hq([page(body)]).value == expected


def test_hq_from_a_legal_notice_page():
    legal = page("<h1>Legal notice</h1><p>Zedly GmbH, Wulfsdorfer Weg 100, 22359 Hamburg, Germany</p>",
                 url="https://acme.test/imprint", topic="legal")
    assert extract.extract_hq([page("<p>Hello.</p>"), legal]).value == {"city": "Hamburg", "country": "Germany"}
