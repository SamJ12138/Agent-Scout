"""Every keyword table the tool uses, in one place.

The extractors contain no keywords of their own: they read these tables.
tests/test_vocab.py has an example sentence for every entry, and fails when an
entry is added without one.

Phrases are matched case-insensitively on word boundaries; a trailing ``*``
allows any word ending ("optimi*" matches optimize, optimise, optimization).
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Which same-site pages to read after the homepage, in priority order.
# A link belongs to a topic when a path segment or its text equals a keyword.
# --------------------------------------------------------------------------
LINK_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("product", ("features", "feature", "product", "products", "platform", "how-it-works", "capabilities")),
    ("integrations", ("integrations", "integration", "connectors", "apps")),
    ("pricing", ("pricing", "plans", "price")),
    ("about", ("about", "about-us", "company", "our-story")),
    ("contact", ("contact", "contact-us")),
    ("customers", ("customers", "case-studies", "customer-stories")),
]

# A link with one of these path segments is never followed.
LINK_EXCLUDED_SEGMENTS: frozenset[str] = frozenset({
    "blog", "news", "press", "careers", "jobs", "login", "log-in", "signin", "sign-in", "signup",
    "sign-up", "register", "legal", "privacy", "terms", "docs", "documentation", "help", "support",
    "status", "cart", "checkout", "search", "tag", "category", "author", "webinars", "events",
    "podcast", "changelog", "community", "forum", "academy", "resources", "download", "downloads",
})

# File extensions that are not pages.
LINK_EXCLUDED_EXTENSIONS: tuple[str, ...] = (
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".zip", ".xml", ".json", ".csv",
    ".mp4", ".mp3", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".ico", ".css", ".js",
)

# --------------------------------------------------------------------------
# Field vocabularies (the exact strings of the ground-truth schema) and the
# phrases that map site text onto them.
# --------------------------------------------------------------------------
CATEGORIES: dict[str, tuple[str, ...]] = {
    "content generation": ("content generation", "content creation", "content generator", "ai writer",
                           "ai writing", "copywriting", "blog posts", "writing assistant", "content marketing"),
    "email marketing": ("email marketing", "email campaigns", "email automation", "newsletters",
                        "cold email", "email outreach", "email sequences"),
    "advertising": ("advertising", "paid ads", "ad campaigns", "google ads", "meta ads", "facebook ads",
                    "ppc", "paid media", "paid social", "ad spend", "performance marketing"),
    "seo": ("seo", "search engine optimi*", "organic traffic", "keyword research", "search rankings",
            "answer engine optimi*"),
    "social media": ("social media", "social posts", "social scheduling", "social content"),
    "sales & crm": ("crm", "sales outreach", "sales pipeline", "lead generation", "sales engagement",
                    "prospecting", "outbound", "sales development"),
    "analytics & reporting": ("analytics", "attribution", "dashboards", "marketing reporting",
                              "marketing intelligence", "data analysis"),
    "customer support": ("customer support", "customer service", "support tickets", "help desk",
                         "support agent*", "chatbot*"),
    "ecommerce": ("ecommerce", "e-commerce", "online store*", "shopify", "product listings",
                  "abandoned cart*", "dtc"),
    "video & creative": ("video generation", "video editing", "ai video*", "image generation",
                         "creative generation", "creative studio", "video ads", "ugc video*", "ai avatars"),
    "general agent platform": ("agent platform", "agent builder", "build ai agents", "build custom agents",
                               "custom agents", "custom ai agents", "no-code agents", "ai workforce",
                               "ai employees", "agentic platform", "platform for ai agents", "ai teammates"),
}

TARGET_USERS: dict[str, tuple[str, ...]] = {
    "marketers": ("marketers", "marketing team*", "marketing leaders", "marketing professionals", "cmo*",
                  "growth team*", "demand gen*", "content team*", "social media managers", "brand team*"),
    "ecommerce brands": ("ecommerce brands", "e-commerce brands", "ecommerce businesses",
                         "e-commerce businesses", "ecommerce teams", "online stores", "online retailers",
                         "shopify merchants", "shopify stores", "dtc brands", "merchants", "retailers",
                         "store owners"),
    "agencies": ("agencies", "agency"),
    "enterprise": ("enterprises", "enterprise teams", "enterprise marketing", "enterprise brands",
                   "enterprise companies", "for enterprise", "large organizations", "fortune 500",
                   "global brands"),
    "small business": ("small business*", "smbs", "small and medium", "startups", "solopreneurs",
                       "small teams", "local businesses", "entrepreneurs"),
    "developers": ("developers", "engineers", "engineering teams", "dev teams"),
    "sales teams": ("sales team*", "sales reps", "sdrs", "revenue teams", "sellers", "account executives",
                    "sales leaders", "revops"),
    "creators": ("creators", "content creators", "influencers", "bloggers"),
}

TASKS: dict[str, tuple[str, ...]] = {
    "write copy": ("copywriting", "ad copy", "body copy", "email copy", "landing page copy", "blog post*",
                   "product description*", "subject lines", "captions", "headlines", "write* content",
                   "draft* content", "generate* content", "content creation", "content generation"),
    "generate images or video": ("generate* images", "image generation", "generate* video*",
                                 "video generation", "ai video*", "ai image*", "ai-generated images",
                                 "create* videos", "ad creatives", "product photos", "ai avatars",
                                 "text to video", "text to image"),
    "send email campaigns": ("email campaign*", "send* emails", "email sequences", "newsletters",
                             "cold emails", "email outreach", "outreach emails", "email automation",
                             "drip campaigns", "email flows"),
    "manage ads": ("ad campaigns", "manage* ads", "ad budgets", "bids", "ad spend", "google ads",
                   "meta ads", "facebook ads", "paid ads", "ppc campaigns", "media buying",
                   "ad optimi*"),
    "seo optimization": ("seo", "search engine optimi*", "keyword research", "keyword suggestions",
                         "optimi* for search", "meta descriptions", "backlinks", "on-page"),
    "schedule social posts": ("schedul* posts", "schedul* social", "social scheduling",
                              "social media scheduling", "publish* posts", "post* to social",
                              "social posts", "content calendar", "auto-post*"),
    "lead qualification": ("lead qualification", "qualif* leads", "qualified leads", "lead scoring",
                           "score* leads", "book* meetings", "prospecting", "lead generation", "lead gen",
                           "lead enrichment"),
    "customer chat": ("chatbot*", "live chat", "customer chat", "chat widget", "conversational ai",
                      "customer conversations", "customer questions", "support tickets"),
    "analytics reporting": ("analytics", "performance report*", "reporting", "reports", "dashboards",
                            "attribution", "kpis"),
    "workflow automation": ("workflow automation", "automat* workflow*", "workflows", "ai workflow*",
                            "agentic workflow*", "any workflow", "automation platform", "automate* tasks",
                            "automations", "no-code automation"),
    "personalization": ("personali*", "hyper-personali*", "one-to-one", "tailored to each"),
    "market research": ("market research", "competitor analysis", "competitive analysis",
                        "competitor research", "competitive intelligence", "audience research",
                        "customer research", "trend analysis", "social listening"),
}

# How many points a vocabulary value needs before it is reported. A phrase
# found in the meta description or a heading scores STRONG_HIT, in an ordinary
# sentence WEAK_HIT. Categories describe what the product is, so one passing
# mention is not enough; audiences and tasks are reported when stated once.
STRONG_HIT = 2
WEAK_HIT = 1
THRESHOLDS = {"categories": 2, "target_user": 1, "tasks": 1}

# A phrase is not read as a statement about the product when
# - one of NEGATIONS stands within NEGATION_WINDOW words before it in the same
#   clause ("is not an SEO tool"),
# - one of POST_NEGATIONS follows it directly ("SEO is not something we do"),
# - the clause is about somebody else: one of OTHERS_SUBJECTS stands before it
#   ("Other tools send campaigns automatically").
NEGATIONS: tuple[str, ...] = ("not", "no", "never", "without", "unlike", "isn't", "doesn't", "don't",
                              "won't", "can't", "cannot", "instead of", "rather than", "nor")
NEGATION_WINDOW = 6
POST_NEGATIONS: tuple[str, ...] = ("is not", "are not", "was not", "were not", "isn't", "aren't",
                                   "wasn't", "weren't", "is no longer", "are no longer", "is never",
                                   "are never")
OTHERS_SUBJECTS: tuple[str, ...] = ("other tools", "other platforms", "other products", "other agents",
                                    "other vendors", "most tools", "most platforms", "most products",
                                    "competitors", "traditional tools", "legacy tools", "unlike")

# A sentence that opens with one of these words, or ends with a question mark,
# asks or frames something ("Why multi-agent systems fail"); it does not assert
# that the product acts by itself or uses several agents.
RHETORICAL_OPENERS: tuple[str, ...] = ("why", "how", "what", "when", "which", "who", "should", "do",
                                       "does", "is", "are", "can", "could", "will", "would")

# An audience word after one of these is something the product is compared
# with or replaces ("cheaper than an agency", "faster than hiring engineers").
AUDIENCE_COMPARISONS: tuple[str, ...] = ("than", "replace*", "replacing", "hire", "hiring", "instead of",
                                         "alternative to", "like having", "like a", "like an")
AUDIENCE_COMPARISON_WINDOW = 5

# --------------------------------------------------------------------------
# can_execute (three-valued) and multi_agent (true or unknown).
#
# TRUE needs one sentence with an action verb, an object in another system or
# channel, and either an autonomy marker or an agent as the acting subject.
# The verb does not count when "you"/"your" stands just before it ("for you to
# send", "so you can publish"): then the person acts.
#
# FALSE needs an unambiguous statement that the product only drafts:
# - one of DRAFT_ONLY_PHRASES, or
# - a negated action (NEGATORS + DRAFT_ONLY_VERBS) about everything: the verb
#   is followed by nothing, by a general object (GENERAL_OBJECTS), or by one of
#   SELF_MARKERS, and then the clause ends. "never sends duplicate emails"
#   (a specific object) and "never sends anything without your approval"
#   (a condition) are not such statements.
# --------------------------------------------------------------------------
EXECUTE_VERBS: tuple[str, ...] = ("send*", "publish*", "schedul*", "launch*", "post*", "adjust*",
                                  "optimi*", "update*", "paus*", "execut*", "deploy*", "repl*",
                                  "respond*", "book*", "run*")
EXECUTE_OBJECTS: tuple[str, ...] = ("campaign*", "email*", "post*", "ads", "ad", "bids", "budget*", "crm",
                                    "messages", "content", "meetings", "newsletters", "replies",
                                    "tickets", "channels")
AUTONOMY_MARKERS: tuple[str, ...] = ("automatically", "autonomously", "on its own", "by itself",
                                     "on your behalf", "for you", "on autopilot", "without human*",
                                     "without manual*", "without anyone", "hands-free", "end-to-end",
                                     "around the clock", "24/7", "while you sleep")
AGENT_SUBJECTS: tuple[str, ...] = ("agent", "agents")
# With an agent as subject, these words mean the person still does the action.
ASSIST_WORDS: tuple[str, ...] = ("help*", "let*", "assist*", "suggest*", "recommend*", "draft*",
                                 "you can", "so you can", "enabl*", "empower*")
# The person is the one acting when one of these stands within
# USER_SUBJECT_WINDOW words before the verb.
USER_SUBJECTS: tuple[str, ...] = ("you", "your")
USER_SUBJECT_WINDOW = 3

DRAFT_ONLY_PHRASES: tuple[str, ...] = ("only drafts", "drafts only", "only suggests", "suggestions only",
                                       "a human must send", "a human must publish", "a human must post",
                                       "a human must press send", "does not take action*",
                                       "never takes action*")
NEGATORS: tuple[str, ...] = ("never", "does not", "doesn't", "do not", "don't", "will not", "won't",
                             "cannot", "can't")
DRAFT_ONLY_VERBS: tuple[str, ...] = ("send", "publish", "post", "launch", "schedule", "execute")
GENERAL_OBJECTS: tuple[str, ...] = ("anything", "emails", "email", "posts", "campaigns", "messages",
                                    "content", "ads", "it", "them")
SELF_MARKERS: tuple[str, ...] = ("for you", "on your behalf", "by itself", "on its own", "automatically",
                                 "itself")

MULTI_AGENT_PHRASES: tuple[str, ...] = ("multi agent", "multiagent", "multiple agents", "team of agents",
                                        "team of ai agents", "team of specialized agents",
                                        "team of specialised agents", "agent team*", "agents work together",
                                        "agents working together", "agent work together",
                                        "agents collaborat*", "collaborating agents", "orchestrat* agents",
                                        "agent orchestration", "orchestration of agents", "swarm of agents",
                                        "agent swarm*", "crew of agents")

# --------------------------------------------------------------------------
# Integrations.
# --------------------------------------------------------------------------
# In a sentence, the names after one of these are read as integrations.
INTEGRATION_TRIGGERS: tuple[str, ...] = ("integrates with", "integrate with", "integrations with",
                                         "integration with", "connects to", "connects with", "connect to",
                                         "works with", "syncs with", "sync with", "plugs into")
# Words that end an image description without being part of the product name.
LOGO_SUFFIXES: tuple[str, ...] = ("logo", "icon", "integration", "logotype")
# Capitalised words that can follow a trigger without naming a product.
NOT_A_PRODUCT: frozenset[str] = frozenset({
    "your", "our", "the", "all", "any", "every", "more", "many", "other", "others", "them", "it", "you",
    "everything", "anything", "popular", "leading", "existing", "favorite", "favourite", "tools", "apps",
    "ai", "crm", "cms", "api", "apis",
})

# Product names recognised wherever integrations are listed. Canonical
# spelling -> other spellings seen on sites.
KNOWN_INTEGRATIONS: dict[str, tuple[str, ...]] = {
    "ActiveCampaign": (), "Adobe Analytics": (), "Ahrefs": (), "Airtable": (), "Amazon": (),
    "Amplitude": (), "Apollo": ("Apollo.io",), "Asana": (), "Attio": (), "BigCommerce": (),
    "BigQuery": ("Google BigQuery",), "Bing Ads": ("Microsoft Ads", "Microsoft Advertising"),
    "Box": (), "Braze": (), "Calendly": (), "Canva": (), "ClickUp": (), "Contentful": (),
    "Customer.io": (), "Discord": (), "Dropbox": (), "Drupal": (), "Facebook": (),
    "Facebook Ads": (), "Figma": (), "GitHub": (), "Gmail": (), "Gong": (),
    "Google Ads": (), "Google Analytics": ("Google Analytics 4", "GA4"), "Google Calendar": (),
    "Google Docs": (), "Google Drive": (), "Google Search Console": (), "Google Sheets": (),
    "HubSpot": (), "Instagram": (), "Intercom": (), "Iterable": (), "Jira": (), "Klaviyo": (),
    "Linear": (), "LinkedIn": (), "LinkedIn Ads": (), "Looker": (), "Magento": ("Adobe Commerce",),
    "Mailchimp": (), "Make": ("Make.com",), "Marketo": ("Adobe Marketo", "Adobe Marketo Engage"),
    "Meta": (), "Meta Ads": (), "Microsoft Dynamics 365": ("Dynamics 365", "Microsoft Dynamics"),
    "Microsoft Teams": ("Teams",), "Mixpanel": (), "Monday.com": ("monday",), "n8n": (),
    "Notion": (), "Outlook": ("Microsoft Outlook",), "Outreach": (), "Pardot": (), "Pinterest": (),
    "Pipedrive": (), "Reddit": (), "Salesforce": (), "Salesloft": (), "Sanity": (), "Segment": (),
    "Semrush": (), "SendGrid": (), "Shopify": (), "Slack": (), "Snapchat": (), "Snowflake": (),
    "Stripe": (), "Tableau": (), "Telegram": (), "TikTok": (), "TikTok Ads": (), "Trello": (),
    "Twilio": (), "Webflow": (), "WhatsApp": (), "WooCommerce": (), "WordPress": (),
    "X": ("Twitter", "X (Twitter)", "Twitter/X", "X/Twitter"), "YouTube": (), "Zapier": (),
    "Zendesk": (), "Zoho CRM": ("Zoho",), "Zoom": (),
}

# --------------------------------------------------------------------------
# Pricing.
# --------------------------------------------------------------------------
FREE_TIER_PHRASES: tuple[str, ...] = ("free plan", "free tier", "free forever", "free trial", "free version",
                                      "free account", "start for free", "start free", "try for free",
                                      "try it free", "try free", "get started for free", "get started free",
                                      "free to start", "sign up free", "sign up for free", "freemium")
# A denial only when the clause ends right after it ("There is no free plan."):
# "No free trial limits." denies limits, not the trial.
NO_FREE_TIER_PHRASES: tuple[str, ...] = ("no free plan", "no free trial", "no free tier", "no free version",
                                         "not offer a free plan", "not offer a free trial",
                                         "not offer a free tier", "not offer a free version")
# A price of zero next to one of these words is a fee that happens to be
# zero, not a free plan ("Setup fee: $0").
NOT_A_FREE_PLAN: tuple[str, ...] = ("fee", "fees", "setup", "onboarding", "shipping", "commission",
                                    "deposit", "tax")
# An amount right after one of these words, or right before one of the second
# list, is a saving, a credit or a funding round, not a price.
NOT_A_PRICE_BEFORE: tuple[str, ...] = ("save", "saves", "saved", "saving", "savings", "worth", "up to",
                                       "over", "raised", "raise")
NOT_A_PRICE_AFTER: tuple[str, ...] = ("off", "discount", "credit", "credits", "million", "billion",
                                      "in revenue", "in sales")
# Outside a pricing page a price only counts next to one of these.
PRICE_CUES: tuple[str, ...] = ("starts at", "starting at", "start at", "starting from", "plans start",
                               "pricing starts", "plans from", "as low as", "from just", "priced at")

# --------------------------------------------------------------------------
# Headquarters.
# --------------------------------------------------------------------------
# "<cue> City, Country" in a sentence states where the company is.
HQ_CUES: tuple[str, ...] = ("headquartered in", "headquarters in", "headquarters are in",
                            "head office in", "head office is in", "based in", "based out of",
                            "hq in", "hq:", "headquarters:")
# A cue after one of these words is about somebody else's office ("Our
# customer Fjordline, based in Berlin, ...").
THIRD_PARTIES: tuple[str, ...] = ("customer", "customers", "client", "clients", "partner", "partners",
                                  "investor", "investors", "user", "users", "agency", "agencies",
                                  "reseller", "resellers", "brand", "brands")

# --------------------------------------------------------------------------
# Parts of a page that are not the site speaking about its product. Matched
# against the words of an element's class and id ("main-menu" -> main, menu).
# --------------------------------------------------------------------------
NAVIGATION_CLASS_WORDS: frozenset[str] = frozenset({
    "nav", "navbar", "navigation", "menu", "menus", "breadcrumb", "breadcrumbs", "megamenu",
})
TESTIMONIAL_CLASS_WORDS: frozenset[str] = frozenset({
    "testimonial", "testimonials", "review", "reviews", "quote", "quotes", "blockquote",
})
CONSENT_CLASS_WORDS: frozenset[str] = frozenset({
    "cookie", "cookies", "consent", "gdpr", "onetrust", "cookiebot", "cmp",
})
# A heading with one of these words belongs to a consent banner, not to the product.
CONSENT_HEADING_WORDS: tuple[str, ...] = ("cookie", "cookies", "privacy", "consent")

# Words that follow a cue without being a city.
NOT_A_CITY: frozenset[str] = frozenset({
    "europe", "asia", "africa", "america", "north america", "south america", "latin america", "emea",
    "apac", "silicon valley", "the bay area", "bay area",
})
