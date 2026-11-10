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
