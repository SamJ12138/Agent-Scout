"""Every keyword-table entry has an example sentence here, and the test fails
when an entry is added to agent_scout/vocab.py without one."""

import pytest

from agent_scout import vocab
from agent_scout.textmatch import has_phrase, is_negated, labels_in, phrase_regex

# table name -> phrase -> a sentence a site might write
EXAMPLES = {
    "CATEGORIES": {
        "content generation": "Content generation for busy teams.",
        "content creation": "Scale content creation without hiring.",
        "content generator": "The content generator learns your tone.",
        "ai writer": "An AI writer that knows your brand.",
        "ai writing": "AI writing that sounds human.",
        "copywriting": "Copywriting on demand.",
        "blog posts": "Publish blog posts every week.",
        "writing assistant": "Your writing assistant for marketing.",
        "content marketing": "Content marketing, automated.",
        "email marketing": "Email marketing that runs itself.",
        "email campaigns": "Plan email campaigns in minutes.",
        "email automation": "Email automation for stores.",
        "newsletters": "Send newsletters your readers open.",
        "cold email": "Cold email that gets replies.",
        "email outreach": "Email outreach at scale.",
        "email sequences": "Build email sequences in one click.",
        "advertising": "Advertising that pays for itself.",
        "paid ads": "Run paid ads on every channel.",
        "ad campaigns": "Launch ad campaigns faster.",
        "google ads": "Optimised for Google Ads.",
        "meta ads": "Creative testing for Meta Ads.",
        "facebook ads": "Scale Facebook Ads profitably.",
        "ppc": "PPC management by an agent.",
        "paid media": "Paid media, planned by AI.",
        "paid social": "Paid social that converts.",
        "ad spend": "Cut wasted ad spend.",
        "performance marketing": "Performance marketing on autopilot.",
        "seo": "SEO for growing companies.",
        "search engine optimi*": "Search engine optimisation made simple.",
        "organic traffic": "Grow organic traffic every month.",
        "keyword research": "Keyword research in seconds.",
        "search rankings": "Improve your search rankings.",
        "answer engine optimi*": "Answer engine optimization for AI search.",
        "social media": "Social media handled for you.",
        "social posts": "A month of social posts in an hour.",
        "social scheduling": "Social scheduling without the spreadsheet.",
        "social content": "Social content your audience shares.",
        "crm": "A CRM that updates itself.",
        "sales outreach": "Sales outreach that feels personal.",
        "sales pipeline": "Fill your sales pipeline.",
        "lead generation": "Lead generation on autopilot.",
        "sales engagement": "A sales engagement platform.",
        "prospecting": "Prospecting done by agents.",
        "outbound": "Outbound that books meetings.",
        "sales development": "Automated sales development.",
        "analytics": "Marketing analytics in one place.",
        "attribution": "Attribution you can trust.",
        "dashboards": "Dashboards for every channel.",
        "marketing reporting": "Marketing reporting without spreadsheets.",
        "marketing intelligence": "A marketing intelligence platform.",
        "data analysis": "Data analysis in plain English.",
        "customer support": "Customer support that never sleeps.",
        "customer service": "Customer service agents for retail.",
        "support tickets": "Resolve support tickets instantly.",
        "help desk": "An AI help desk.",
        "support agent*": "AI support agents for your store.",
        "chatbot*": "Chatbots that sell.",
        "ecommerce": "Built for ecommerce.",
        "e-commerce": "The e-commerce growth agent.",
        "online store*": "Grow your online store.",
        "shopify": "Made for Shopify.",
        "product listings": "Better product listings.",
        "abandoned cart*": "Recover abandoned carts.",
        "dtc": "The DTC marketing agent.",
        "video generation": "Video generation for ads.",
        "video editing": "Video editing by AI.",
        "ai video*": "AI videos in minutes.",
        "image generation": "Image generation for brands.",
        "creative generation": "Creative generation at scale.",
        "creative studio": "A creative studio in your browser.",
        "video ads": "Video ads that convert.",
        "ugc video*": "UGC videos without creators.",
        "ai avatars": "AI avatars for every language.",
        "agent platform": "The agent platform for marketing.",
        "agent builder": "A visual agent builder.",
        "build ai agents": "Build AI agents without code.",
        "build custom agents": "Build custom agents for your team.",
        "custom agents": "Deploy custom agents in a day.",
        "custom ai agents": "Custom AI agents for every task.",
        "no-code agents": "No-code agents for operations.",
        "ai workforce": "Your AI workforce.",
        "ai employees": "Hire AI employees.",
        "agentic platform": "An agentic platform for growth.",
        "platform for ai agents": "The platform for AI agents.",
        "ai teammates": "AI teammates that do the work.",
    },
    "TARGET_USERS": {
        "marketers": "Built for marketers.",
        "marketing team*": "Marketing teams ship faster.",
        "marketing leaders": "Trusted by marketing leaders.",
        "marketing professionals": "For marketing professionals.",
        "cmo*": "What CMOs need to know.",
        "growth team*": "Growth teams love it.",
        "demand gen*": "For demand generation leaders.",
        "content team*": "Content teams publish more.",
        "social media managers": "Made for social media managers.",
        "brand team*": "Brand teams stay consistent.",
        "ecommerce brands": "For ecommerce brands.",
        "e-commerce brands": "Helping e-commerce brands grow.",
        "ecommerce businesses": "Ecommerce businesses of every size.",
        "e-commerce businesses": "E-commerce businesses use it daily.",
        "ecommerce teams": "Ecommerce teams save hours.",
        "online stores": "For online stores.",
        "online retailers": "Online retailers sell more.",
        "shopify merchants": "Loved by Shopify merchants.",
        "shopify stores": "For Shopify stores.",
        "dtc brands": "DTC brands scale with us.",
        "merchants": "Merchants see results in a week.",
        "retailers": "Retailers of all sizes.",
        "store owners": "Store owners save time.",
        "agencies": "For agencies with many clients.",
        "agency": "Run your agency on one platform.",
        "enterprises": "Enterprises trust us.",
        "enterprise teams": "Enterprise teams collaborate here.",
        "enterprise marketing": "Enterprise marketing, simplified.",
        "enterprise brands": "Enterprise brands rely on it.",
        "enterprise companies": "Enterprise companies deploy in weeks.",
        "for enterprise": "Agents for enterprise.",
        "large organizations": "Designed for large organizations.",
        "fortune 500": "Used by Fortune 500 teams.",
        "global brands": "Global brands run on it.",
        "small business*": "Perfect for small businesses.",
        "smbs": "Built for SMBs.",
        "small and medium": "For small and medium companies.",
        "startups": "Startups launch faster.",
        "solopreneurs": "Solopreneurs do more alone.",
        "small teams": "Small teams punch above their weight.",
        "local businesses": "Local businesses get found.",
        "entrepreneurs": "For entrepreneurs.",
        "developers": "Developers extend it with the API.",
        "engineers": "Engineers love the SDK.",
        "engineering teams": "For engineering teams.",
        "dev teams": "Dev teams integrate in a day.",
        "sales team*": "Sales teams close faster.",
        "sales reps": "Sales reps save two hours a day.",
        "sdrs": "SDRs book more meetings.",
        "revenue teams": "Revenue teams align here.",
        "sellers": "Sellers focus on selling.",
        "account executives": "Account executives prepare in minutes.",
        "sales leaders": "Sales leaders see the pipeline.",
        "revops": "RevOps keeps data clean.",
        "creators": "For creators.",
        "content creators": "Content creators post daily.",
        "influencers": "Influencers grow faster.",
        "bloggers": "Bloggers rank higher.",
    },
    "TASKS": {
        "copywriting": "Copywriting for every channel.",
        "ad copy": "Writes ad copy that converts.",
        "body copy": "It writes the body copy.",
        "email copy": "Generates email copy.",
        "landing page copy": "Landing page copy in seconds.",
        "blog post*": "Drafts a blog post from a brief.",
        "product description*": "Writes product descriptions.",
        "subject lines": "Tests subject lines.",
        "captions": "Writes captions for each post.",
        "headlines": "Suggests ten headlines.",
        "write* content": "It writes content for your site.",
        "draft* content": "Drafts content in your voice.",
        "generate* content": "Generates content daily.",
        "content creation": "Content creation at scale.",
        "content generation": "Content generation for teams.",
        "generate* images": "It generates images for ads.",
        "image generation": "Image generation built in.",
        "generate* video*": "Generates videos from a script.",
        "video generation": "Video generation in minutes.",
        "ai video*": "AI video for every product.",
        "ai image*": "AI images on brand.",
        "ai-generated images": "AI-generated images for listings.",
        "create* videos": "Creates videos from product pages.",
        "ad creatives": "Fresh ad creatives every week.",
        "product photos": "Studio-quality product photos.",
        "ai avatars": "AI avatars present your product.",
        "text to video": "Text to video in one step.",
        "text to image": "Text-to-image for marketers.",
        "email campaign*": "Sends an email campaign each week.",
        "send* emails": "It sends emails at the right time.",
        "email sequences": "Runs email sequences.",
        "newsletters": "Writes and sends newsletters.",
        "cold emails": "Sends cold emails that land.",
        "email outreach": "Email outreach handled.",
        "outreach emails": "Sends outreach emails daily.",
        "email automation": "Email automation included.",
        "drip campaigns": "Sets up drip campaigns.",
        "email flows": "Builds email flows.",
        "ad campaigns": "Launches ad campaigns.",
        "manage* ads": "It manages ads across networks.",
        "ad budgets": "Shifts ad budgets daily.",
        "bids": "Adjusts bids every hour.",
        "ad spend": "Optimises ad spend.",
        "google ads": "Runs your Google Ads.",
        "meta ads": "Manages Meta Ads.",
        "facebook ads": "Optimises Facebook Ads.",
        "paid ads": "Handles paid ads.",
        "ppc campaigns": "Manages PPC campaigns.",
        "media buying": "Automated media buying.",
        "ad optimi*": "Continuous ad optimization.",
        "seo": "Handles SEO.",
        "search engine optimi*": "Search engine optimization included.",
        "keyword research": "Does keyword research.",
        "keyword suggestions": "Gives keyword suggestions.",
        "optimi* for search": "Every page is optimised for search.",
        "meta descriptions": "Writes meta descriptions.",
        "backlinks": "Finds backlinks.",
        "on-page": "Fixes on-page issues.",
        "schedul* posts": "Schedules posts for the week.",
        "schedul* social": "Scheduling social updates is automatic.",
        "social scheduling": "Social scheduling built in.",
        "social media scheduling": "Social media scheduling for teams.",
        "publish* posts": "Publishes posts to every channel.",
        "post* to social": "Posts to social networks.",
        "social posts": "Creates social posts.",
        "content calendar": "Fills your content calendar.",
        "auto-post*": "Auto-posting to all networks.",
        "lead qualification": "Lead qualification in real time.",
        "qualif* leads": "Qualifies leads as they arrive.",
        "qualified leads": "Hands over qualified leads.",
        "lead scoring": "Lead scoring by AI.",
        "score* leads": "Scores leads automatically.",
        "book* meetings": "Books meetings on your calendar.",
        "prospecting": "Prospecting, automated.",
        "lead generation": "Lead generation at scale.",
        "lead gen": "Lead gen without forms.",
        "lead enrichment": "Lead enrichment from public data.",
        "chatbot*": "A chatbot for your store.",
        "live chat": "Live chat handled by AI.",
        "customer chat": "Customer chat on every page.",
        "chat widget": "Add the chat widget.",
        "conversational ai": "Conversational AI for sales.",
        "customer conversations": "Handles customer conversations.",
        "customer questions": "Answers customer questions.",
        "support tickets": "Resolves support tickets.",
        "analytics": "Analytics for every campaign.",
        "performance report*": "A performance report every week.",
        "reporting": "Reporting built in.",
        "reports": "Weekly reports by email.",
        "dashboards": "Live dashboards.",
        "attribution": "Multi-touch attribution.",
        "kpis": "Tracks your KPIs.",
        "workflow automation": "Workflow automation for marketing.",
        "automat* workflow*": "Automate workflows end to end.",
        "workflows": "Chain steps into workflows.",
        "ai workflow*": "AI workflows for content.",
        "agentic workflow*": "Agentic workflows that run daily.",
        "any workflow": "An agent for any workflow.",
        "automation platform": "The automation platform for growth.",
        "automate* tasks": "Automates tasks you repeat.",
        "automations": "Build automations in minutes.",
        "no-code automation": "No-code automation.",
        "personali*": "Personalized messages for each shopper.",
        "hyper-personali*": "Hyper-personalised outreach.",
        "one-to-one": "One-to-one messaging at scale.",
        "tailored to each": "Offers tailored to each visitor.",
        "market research": "Market research in minutes.",
        "competitor analysis": "Competitor analysis on demand.",
        "competitive analysis": "Competitive analysis reports.",
        "competitor research": "Competitor research by agents.",
        "competitive intelligence": "Competitive intelligence feeds.",
        "audience research": "Audience research for campaigns.",
        "customer research": "Customer research synthesis.",
        "trend analysis": "Trend analysis every morning.",
        "social listening": "Social listening across networks.",
    },
    "MULTI_AGENT_PHRASES": {
        "multi agent": "A multi-agent system for marketing.",
        "multiagent": "Our multiagent architecture.",
        "multiple agents": "Multiple agents share one brief.",
        "team of agents": "A team of agents runs your campaigns.",
        "team of ai agents": "A team of AI agents at work.",
        "team of specialized agents": "A team of specialized agents.",
        "team of specialised agents": "A team of specialised agents.",
        "agent team*": "Agent teams for every channel.",
        "agents work together": "The agents work together.",
        "agents working together": "Agents working together on one goal.",
        "agent work together": "A writer agent and an editor agent work together.",
        "agents collaborat*": "Agents collaborate on each campaign.",
        "collaborating agents": "A set of collaborating agents.",
        "orchestrat* agents": "It orchestrates agents across tools.",
        "agent orchestration": "Agent orchestration built in.",
        "orchestration of agents": "Orchestration of agents at scale.",
        "swarm of agents": "A swarm of agents.",
        "agent swarm*": "Agent swarms for research.",
        "crew of agents": "A crew of agents.",
    },
    "DRAFT_ONLY_PHRASES": {
        "only drafts": "The tool only drafts.",
        "drafts only": "Drafts only: you publish.",
        "only suggests": "It only suggests changes.",
        "suggestions only": "Suggestions only, never actions.",
        "a human must send": "A human must send each message.",
        "a human must publish": "A human must publish the post.",
        "a human must post": "A human must post it.",
        "a human must press send": "A human must press send.",
        "does not take action*": "It does not take actions in your accounts.",
        "never takes action*": "It never takes action on its own.",
    },
    "AUTONOMY_MARKERS": {
        "automatically": "Sends automatically.",
        "autonomously": "Runs autonomously.",
        "on its own": "Acts on its own.",
        "by itself": "Works by itself.",
        "on your behalf": "Replies on your behalf.",
        "for you": "Posts for you.",
        "on autopilot": "Campaigns on autopilot.",
        "without human*": "Runs without human input.",
        "without manual*": "Works without manual steps.",
        "without anyone": "Goes out without anyone pressing send.",
        "hands-free": "Hands-free publishing.",
        "end-to-end": "Handles campaigns end-to-end.",
        "around the clock": "Publishes around the clock.",
        "24/7": "Works 24/7.",
        "while you sleep": "Sends while you sleep.",
    },
    "INTEGRATION_TRIGGERS": {
        "integrates with": "It integrates with Slack.",
        "integrate with": "Integrate with Slack.",
        "integrations with": "Native integrations with Slack.",
        "integration with": "Deep integration with Slack.",
        "connects to": "It connects to Slack.",
        "connects with": "It connects with Slack.",
        "connect to": "Connect to Slack.",
        "works with": "Works with Slack.",
        "syncs with": "Syncs with Slack.",
        "sync with": "Two-way sync with Slack.",
        "plugs into": "Plugs into Slack.",
    },
    "FREE_TIER_PHRASES": {
        "free plan*": "Start on the free plan.",
        "free tier*": "A generous free tier.",
        "free forever": "Free forever for one user.",
        "free trial*": "Free trials on every plan.",
        "free version*": "Use the free version.",
        "free account": "Create a free account.",
        "start for free": "Start for free",
        "start free": "Start free",
        "try for free": "Try for free",
        "try it free": "Try it free",
        "try free": "Try free for 7 days",
        "get started for free": "Get started for free",
        "get started free": "Get started free",
        "free to start": "Free to start.",
        "sign up free": "Sign up free",
        "sign up for free": "Sign up for free",
        "freemium": "A freemium model.",
    },
    "PRICE_CUES": {
        "starts at": "Pricing starts at $20/month.",
        "starting at": "Starting at $20/month.",
        "start at": "Plans start at $20/month.",
        "starting from": "Starting from $20/month.",
        "plans start": "Plans start from $20.",
        "pricing starts": "Pricing starts low.",
        "plans from": "Plans from $20/month.",
        "as low as": "As low as $20/month.",
        "from just": "From just $20/month.",
        "priced at": "Priced at $20/month.",
    },
    "HQ_CUES": {
        "headquartered in": "We are headquartered in Austin, Texas.",
        "headquarters in": "With headquarters in Berlin, Germany.",
        "headquarters are in": "Our headquarters are in Paris, France.",
        "head office in": "Head office in Dublin, Ireland.",
        "head office is in": "Our head office is in Dublin, Ireland.",
        "based in": "Based in Toronto, Canada.",
        "based out of": "Based out of Sydney, Australia.",
        "hq in": "HQ in London, UK.",
        "hq:": "HQ: London, UK",
        "headquarters:": "Headquarters: London, UK",
    },
}

TABLES = {name: getattr(vocab, name) for name in EXAMPLES}


def _entries():
    for name, table in TABLES.items():
        phrases = [p for group in table.values() for p in group] if isinstance(table, dict) else list(table)
        for phrase in dict.fromkeys(phrases):
            yield name, phrase


@pytest.mark.parametrize("table, phrase", list(_entries()))
def test_every_entry_has_an_example_that_it_matches(table, phrase):
    assert phrase in EXAMPLES[table], f"add an example sentence for {table}: {phrase!r}"
    assert phrase_regex(phrase).search(EXAMPLES[table][phrase]), (phrase, EXAMPLES[table][phrase])


def test_no_example_refers_to_a_removed_entry():
    for name, examples in EXAMPLES.items():
        current = {phrase for table, phrase in _entries() if table == name}
        assert set(examples) <= current, (name, set(examples) - current)


def test_labels_are_exactly_the_schema_vocabularies():
    assert list(vocab.CATEGORIES) == [
        "content generation", "email marketing", "advertising", "seo", "social media", "sales & crm",
        "analytics & reporting", "customer support", "ecommerce", "video & creative", "general agent platform"]
    assert list(vocab.TARGET_USERS) == [
        "marketers", "ecommerce brands", "agencies", "enterprise", "small business", "developers",
        "sales teams", "creators"]
    assert list(vocab.TASKS) == [
        "write copy", "generate images or video", "send email campaigns", "manage ads", "seo optimization",
        "schedule social posts", "lead qualification", "customer chat", "analytics reporting",
        "workflow automation", "personalization", "market research"]


@pytest.mark.parametrize("verb", vocab.EXECUTE_VERBS)
def test_execute_verbs_match_an_inflected_form(verb):
    stem = verb.rstrip("*")
    assert phrase_regex(verb).search(f"it {stem}s things") or phrase_regex(verb).search(f"it {stem}es things") \
        or phrase_regex(verb).search(f"it {stem}ies things")


@pytest.mark.parametrize("word", vocab.EXECUTE_OBJECTS + vocab.AGENT_SUBJECTS)
def test_single_word_tables_match_themselves(word):
    assert phrase_regex(word).search(f"the {word.rstrip('*')} here")


@pytest.mark.parametrize("word", vocab.ASSIST_WORDS)
def test_assist_words(word):
    assert phrase_regex(word).search(f"it {word.rstrip('*')} here")


@pytest.mark.parametrize("text, table, unwanted", [
    ("Read our address and add your details.", "CATEGORIES", "advertising"),       # "ad" inside words
    ("Our office is in Seoul.", "CATEGORIES", "seo"),
    ("Enterprise", "TARGET_USERS", "enterprise"),                                   # a plan name
    ("Enterprise-grade security.", "TARGET_USERS", "enterprise"),
    ("The copywriters on our team.", "TASKS", "write copy"),
    ("Welcome flows go out daily.", "TASKS", "workflow automation"),
    ("Social captions in your voice.", "CATEGORIES", "social media"),
])
def test_phrases_do_not_match_lookalikes(text, table, unwanted):
    assert unwanted not in labels_in(text, getattr(vocab, table))


@pytest.mark.parametrize("text, phrase, negated", [
    ("Campaign Pilot is not an SEO tool.", "seo", True),
    ("It does not manage social media.", "social media", True),
    ("Unlike tools that publish automatically, we draft.", "automatically", True),
    ("It never touches your ad budgets.", "ad budgets", True),
    ("We don’t do cold email.", "cold email", True),
    ("Great SEO, not guesswork.", "seo", False),                      # negation after the phrase
    ("No code needed. SEO for everyone.", "seo", False),              # negation in another sentence
    ("It writes email copy without anyone asking.", "email copy", False),
])
def test_negation(text, phrase, negated):
    match = phrase_regex(phrase).search(text)
    assert match and is_negated(text, match.start()) is negated
    assert has_phrase(text, [phrase]) is (not negated)


def test_hyphen_and_space_are_interchangeable():
    assert has_phrase("A multi-agent system", ["multi agent"])
    assert has_phrase("text-to-image models", ["text to image"])


@pytest.mark.parametrize("name, aliases", list(vocab.KNOWN_INTEGRATIONS.items()))
def test_known_integrations_resolve_to_their_canonical_name(name, aliases):
    from agent_scout.extract import known_integration
    assert known_integration(name) == name
    assert known_integration(name.upper()) == name
    assert known_integration(f"{name} logo") == name
    for alias in aliases:
        assert known_integration(alias) == name


def test_link_topic_tables_are_disjoint():
    seen = {}
    for topic, keywords in vocab.LINK_TOPICS:
        for keyword in keywords:
            assert keyword not in seen, f"{keyword} is in {seen.get(keyword)} and {topic}"
            assert keyword not in vocab.LINK_EXCLUDED_SEGMENTS
            seen[keyword] = topic


# ------------------------------------------------------------------ tables added after an adversarial review:
# every entry is exercised through the behaviour it exists for
from agent_scout import extract  # noqa: E402
from agent_scout.config import Config  # noqa: E402
from agent_scout.model import UNKNOWN  # noqa: E402
from agent_scout.page import parse_page  # noqa: E402
from agent_scout.textmatch import is_rhetorical  # noqa: E402

FILLER = "<p>" + "Ordinary words that say nothing in particular. " * 6 + "</p>"


def _page(body, url="https://acme.test/", topic="home"):
    html = f"<!doctype html><html><head><title>Acme</title></head><body>{body}{FILLER}</body></html>"
    page = parse_page(url, html, Config())
    page.topic = topic
    return page


@pytest.mark.parametrize("negation", vocab.POST_NEGATIONS)
def test_post_negations_cancel_the_phrase_before_them(negation):
    assert "customer chat" not in labels_in(f"Chatbots {negation} part of the product.", vocab.TASKS)
    assert "customer chat" in labels_in("Chatbots that answer every visitor.", vocab.TASKS)


@pytest.mark.parametrize("subject", vocab.OTHERS_SUBJECTS)
def test_a_clause_about_others_claims_nothing_for_the_product(subject):
    assert labels_in(f"{subject.capitalize()} offer keyword research and call it a day.", vocab.TASKS) == []


@pytest.mark.parametrize("comparison", vocab.AUDIENCE_COMPARISONS)
def test_audience_comparisons(comparison):
    text = f"It works {comparison.rstrip('*')} an agency."
    assert extract.extract_vocab([_page(f"<p>{text}</p>")], "target_user").value == UNKNOWN


@pytest.mark.parametrize("opener", vocab.RHETORICAL_OPENERS)
def test_rhetorical_openers(opener):
    assert is_rhetorical(f"{opener.capitalize()} a team of agents sends campaigns automatically")
    assert not is_rhetorical("A team of agents sends campaigns automatically.")


@pytest.mark.parametrize("negator", vocab.NEGATORS)
@pytest.mark.parametrize("verb", vocab.DRAFT_ONLY_VERBS)
def test_every_negator_and_verb_pair_is_a_draft_only_statement(negator, verb):
    third_person = verb + ("es" if verb.endswith("sh") else "s")
    form = third_person if negator == "never" else verb
    assert extract._states_draft_only(f"The assistant {negator} {form}.")
    assert not extract._states_draft_only(f"The assistant {negator} {form} duplicate things.")


@pytest.mark.parametrize("thing", vocab.GENERAL_OBJECTS)
def test_general_objects(thing):
    assert extract._states_draft_only(f"It never sends {thing}.")
    assert not extract._states_draft_only(f"It never sends {thing} without your approval.")


@pytest.mark.parametrize("marker", vocab.SELF_MARKERS)
def test_self_markers(marker):
    assert extract._states_draft_only(f"It does not post {marker}.")


@pytest.mark.parametrize("subject", vocab.USER_SUBJECTS)
def test_user_subjects(subject):
    sentence = f"With one click {subject} team sends campaigns automatically." if subject == "your" \
        else f"With one click {subject} send campaigns automatically."
    assert not extract._states_execution(sentence)
    assert extract._states_execution("With one click it sends campaigns automatically.")


@pytest.mark.parametrize("word", vocab.THIRD_PARTIES)
def test_third_parties_before_a_headquarters_cue(word):
    body = f"<p>One {word} of ours, based in Oslo, Norway, likes it.</p>"
    assert extract.extract_hq([_page(body)]).value == UNKNOWN


@pytest.mark.parametrize("word", vocab.NOT_A_FREE_PLAN)
def test_a_zero_fee_is_not_a_free_plan(word):
    body = f"<table><tr><td>{word.capitalize()}</td><td>$0</td></tr></table>"
    assert extract.extract_pricing([_page(body, "https://acme.test/pricing", "pricing")]).value == UNKNOWN


@pytest.mark.parametrize("word", vocab.CONSENT_HEADING_WORDS)
def test_consent_headings_are_not_the_hero(word):
    body = f"<h2>Your {word} choices</h2><p>Decide what we may store.</p>"
    assert extract.extract_one_liner([_page(body)]).value == UNKNOWN


@pytest.mark.parametrize("word, zone", [(w, "nav") for w in sorted(vocab.NAVIGATION_CLASS_WORDS)]
                         + [(w, "quote") for w in sorted(vocab.TESTIMONIAL_CLASS_WORDS)]
                         + [(w, "banner") for w in sorted(vocab.CONSENT_CLASS_WORDS)])
def test_class_words_set_the_zone(word, zone):
    page = _page(f"<div class='site-{word} wide'><p>Inside the block.</p></div><p>Outside the block.</p>")
    zones = {snippet.text: snippet.zone for snippet in page.snippets}
    assert zones["Inside the block."] == zone and zones["Outside the block."] == "main"


def _free_tier(sentence):
    value = extract.extract_pricing([_page(f"<p>{sentence}</p>", "https://acme.test/pricing", "pricing")]).value
    return value if value == UNKNOWN else value["free_tier"]


@pytest.mark.parametrize("noun", vocab.FREE_NOUNS)
def test_free_nouns_can_be_denied_and_affirmed(noun):
    assert _free_tier(f"We do not offer {noun}.") is False
    assert _free_tier(f"There is no {noun}.") is False
    assert _free_tier(f"Every account comes with {noun}.") is True


@pytest.mark.parametrize("verb", vocab.OFFER_VERBS)
def test_offer_verbs(verb):
    assert _free_tier(f"Acme does not {verb} a free trial.") is False


@pytest.mark.parametrize("negation", vocab.OFFER_NEGATIONS)
def test_offer_negations(negation):
    assert _free_tier(f"We {negation} offer a free plan.") is False


@pytest.mark.parametrize("phrase", vocab.NOT_AVAILABLE)
def test_not_available(phrase):
    assert _free_tier(f"A free trial is {phrase}.") is False
