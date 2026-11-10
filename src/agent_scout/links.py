"""Choose which pages of a site to read after the homepage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .page import Page
from .vocab import LINK_EXCLUDED_EXTENSIONS, LINK_EXCLUDED_SEGMENTS, LINK_TOPICS


@dataclass
class Candidate:
    url: str
    topic: str
    score: int
    text: str


def _site_key(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    default = {"http": 80, "https": 443}.get(parts.scheme, 0)
    port = parts.port or default
    return host, (0 if port in (80, 443) else port)


def same_site(url: str, home: str) -> bool:
    """Same host (ignoring a leading www.) and port; http and https are one site."""
    return _site_key(url) == _site_key(home)


def page_identity(url: str) -> str:
    parts = urlsplit(url)
    return f"{_site_key(url)}{parts.path.rstrip('/') or '/'}"


def _score(segments: list[str], text: str, keywords: tuple[str, ...]) -> int:
    score = 0
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    for keyword in keywords:
        if segments and segments[-1] == keyword:
            score = max(score, 6)
        elif keyword in segments:
            score = max(score, 4)
        phrase = keyword.replace("-", " ")
        if re.search(rf"(?:^| ){re.escape(phrase)}(?: |$)", words):
            score = max(score, 3) if score < 4 else score + 1
    return score - max(0, len(segments) - 1) if score else 0


def select_links(page: Page, home_url: str) -> list[Candidate]:
    """Ranked same-site links: the best link of each topic, then second bests, ..."""
    per_topic: dict[str, list[Candidate]] = {topic: [] for topic, _ in LINK_TOPICS}
    seen = {page_identity(home_url), page_identity(page.url)}
    order: dict[str, int] = {}
    for position, link in enumerate(page.links):
        parts = urlsplit(link.url)
        if not same_site(link.url, home_url):
            continue
        path = parts.path.lower()
        segments = [segment for segment in path.split("/") if segment]
        if path.endswith(LINK_EXCLUDED_EXTENSIONS) or LINK_EXCLUDED_SEGMENTS.intersection(segments):
            continue
        segments = [re.sub(r"\.(html?|php|aspx?)$", "", segment) for segment in segments]
        identity = page_identity(link.url)
        best_topic, best_score = None, 0
        for topic, keywords in LINK_TOPICS:
            score = _score(segments, link.text, keywords) - (2 if parts.query else 0)
            if score > best_score:
                best_topic, best_score = topic, score
        if best_topic is None:
            continue
        if identity in seen:
            existing = next((c for c in per_topic[best_topic] if page_identity(c.url) == identity), None)
            if existing and best_score > existing.score:
                existing.score = best_score
            continue
        seen.add(identity)
        clean_url = link.url.split("?")[0].rstrip("/") if not parts.query else link.url
        if not urlsplit(clean_url).path:
            clean_url += "/"
        per_topic[best_topic].append(Candidate(clean_url, best_topic, best_score, link.text))
        order[clean_url] = position

    for candidates in per_topic.values():
        candidates.sort(key=lambda c: (-c.score, order[c.url]))
    ranked: list[Candidate] = []
    depth = 0
    while any(len(candidates) > depth for candidates in per_topic.values()):
        for topic, _ in LINK_TOPICS:
            if len(per_topic[topic]) > depth:
                ranked.append(per_topic[topic][depth])
        depth += 1
    return ranked
