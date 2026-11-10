"""Turn fetched HTML into the pieces the extractors read.

Only two kinds of content are kept:

- head data the site wrote for machines: <title>, meta/og tags, JSON-LD;
- visible text, split into snippets that remember how they appeared
  (heading, sentence, link text, table row) and where (nav, footer, main).

Scripts, styles, <noscript> and <template> content are never text. A page
with almost no visible text that loads scripts is flagged ``needs_rendering``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from . import obs
from .config import Config

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
BLOCK_TAGS = frozenset(HEADINGS + (
    "address", "article", "aside", "blockquote", "body", "dd", "details", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "header", "hr", "li", "main", "nav",
    "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
))
INVISIBLE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "head", "title")
ZONE_TAGS = {"nav": "nav", "footer": "footer", "header": "header"}
INLINE_SCRIPT_SHELL_CHARS = 2000   # inline script size that counts as "ships large scripts"

# A heading with one of these phrases starts a section that lists integrations.
INTEGRATION_HEADING = re.compile(
    r"\b(integrat\w*|connectors?|works with|connects? (?:to|with)|plugs? into|your (?:tech )?stack)\b",
    re.IGNORECASE)
INTEGRATION_CLASS = re.compile(r"integration|connector", re.IGNORECASE)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"])")
_NOT_A_SENTENCE_END = re.compile(r"\b(?:[A-Z]\.[A-Z]|Inc|Ltd|Co|Corp|No|vs|e\.g|i\.e|St|Dr|Mr|Ms)\.$")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def inline_text(nodes: list) -> str:
    """Text of inline content exactly as written: no separator is invented
    between inline elements, and a <br> counts as a space."""
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, Tag):
            for br in node.find_all("br"):
                br.replace_with(" ")
            parts.append(" " if node.name == "br" else node.get_text(""))
        else:
            parts.append(str(node))
    return clean("".join(parts))


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for piece in _SENTENCE_END.split(clean(text)):
        if parts and _NOT_A_SENTENCE_END.search(parts[-1]):
            parts[-1] = f"{parts[-1]} {piece}"
        elif piece:
            parts.append(piece)
    return parts


@dataclass
class Snippet:
    text: str
    method: str          # meta | heading | sentence | link | table
    zone: str            # head | nav | header | footer | main
    in_integration_section: bool = False


@dataclass
class Link:
    url: str
    text: str
    zone: str
    in_integration_section: bool = False


@dataclass
class Image:
    alt: str
    zone: str
    in_integration_section: bool = False


@dataclass
class Page:
    url: str
    topic: str = "home"      # which link topic led here: home | product | integrations | pricing | ...
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict] = field(default_factory=list)
    snippets: list[Snippet] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    visible_chars: int = 0
    inline_script_chars: int = 0
    external_scripts: int = 0
    needs_rendering: bool = False

    def text(self) -> str:
        """All text a quote may come from: head data plus visible text."""
        parts = [self.title, *self.meta.values(), *(s.text for s in self.snippets), *self.addresses,
                 *(image.alt for image in self.images)]
        return "\n".join(part for part in parts if part)


def _flatten_json_ld(node, out: list[dict]) -> None:
    if isinstance(node, list):
        for item in node:
            _flatten_json_ld(item, out)
    elif isinstance(node, dict):
        if "@type" in node:
            out.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                _flatten_json_ld(value, out)


def _zone(element: Tag) -> str:
    for parent in [element, *element.parents]:
        if isinstance(parent, Tag) and parent.name in ZONE_TAGS:
            return ZONE_TAGS[parent.name]
    return "main"


def _heading_level(tag: Tag) -> int:
    return int(tag.name[1])


def _integration_containers(soup: BeautifulSoup) -> set[int]:
    """ids of elements whose contents are presented as a list of integrations."""
    containers: set[int] = set()
    for element in soup.find_all(True):
        marker = " ".join(element.get("class") or []) + " " + (element.get("id") or "")
        if INTEGRATION_CLASS.search(marker):
            containers.add(id(element))
    for heading in soup.find_all(HEADINGS):
        if not INTEGRATION_HEADING.search(heading.get_text(" ")):
            continue
        parent = heading.parent
        sibling_headings = [h for h in parent.find_all(HEADINGS, recursive=False)] if parent else []
        if parent is None or parent.name in ("body", "main", "article") or len(sibling_headings) > 1:
            for sibling in heading.next_siblings:
                if isinstance(sibling, Tag):
                    if sibling.name in HEADINGS and _heading_level(sibling) <= _heading_level(heading):
                        break
                    containers.add(id(sibling))
        else:
            containers.add(id(parent))
    return containers


def parse_page(url: str, html: str, config: Config) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    page = Page(url=url)

    if soup.title and soup.title.string:
        page.title = clean(soup.title.string)
    for tag in soup.find_all("meta"):
        key = (tag.get("name") or tag.get("property") or "").strip().lower()
        content = clean(tag.get("content") or "")
        if key and content and key not in page.meta:
            page.meta[key] = content

    for script in soup.find_all("script"):
        kind = (script.get("type") or "").lower()
        body = script.string or script.get_text() or ""
        if kind == "application/ld+json":
            try:
                _flatten_json_ld(json.loads(body), page.json_ld)
            except (json.JSONDecodeError, RecursionError):
                obs.emit("parse", "skip", error_type="json_ld_invalid", url=url)
        elif script.get("src"):
            page.external_scripts += 1
        else:
            page.inline_script_chars += len(body)

    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()
    containers = _integration_containers(soup)

    def in_integration(element: Tag) -> bool:
        return any(id(parent) in containers for parent in [element, *element.parents])

    for image in soup.find_all("img"):
        alt = clean(image.get("alt") or "")
        if alt:
            page.images.append(Image(alt=alt, zone=_zone(image), in_integration_section=in_integration(image)))

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        try:
            absolute = urljoin(url, href).split("#")[0]
            parts = urlsplit(absolute)
            parts.port                      # raises on a malformed host or port
        except ValueError:
            obs.emit("parse", "skip", error_type="bad_link", url=url, href=href[:200])
            continue
        if parts.scheme not in ("http", "https") or not parts.hostname or href.startswith("#"):
            continue
        text = inline_text([anchor]) if not anchor.find(list(BLOCK_TAGS)) else clean(anchor.get_text(" "))
        if not text:
            inner = anchor.find("img")
            text = clean((inner.get("alt") if inner else None) or anchor.get("aria-label") or anchor.get("title") or "")
        page.links.append(Link(url=absolute, text=text, zone=_zone(anchor),
                               in_integration_section=in_integration(anchor)))

    for element in soup.find_all(INVISIBLE_TAGS):
        element.decompose()

    def has_block_child(element: Tag) -> bool:
        return element.find(list(BLOCK_TAGS)) is not None

    def link_only(nodes: list) -> bool:
        """True when all the text in ``nodes`` sits inside <a> or <button>."""
        loose = ""
        for node in nodes:
            if isinstance(node, NavigableString):
                loose += str(node)
            elif node.name not in ("a", "button"):
                inner = "".join(str(s) for s in node.find_all(string=True)
                                if not any(p.name in ("a", "button") for p in s.parents if p is not node.parent))
                loose += inner
        return not clean(loose)

    def emit_text(nodes: list, anchor: Tag, heading: bool = False) -> None:
        text = inline_text(nodes)
        if not text:
            return
        page.visible_chars += len(text)
        zone, integ = _zone(anchor), in_integration(anchor)
        if heading:
            page.snippets.append(Snippet(text, "heading", zone, integ))
        elif link_only(nodes):
            page.snippets.append(Snippet(text, "link", zone, integ))
        else:
            for sentence in split_sentences(text):
                page.snippets.append(Snippet(sentence, "sentence", zone, integ))

    def visit(element: Tag) -> None:
        if element.name == "table":
            rows = []
            for row in element.find_all("tr"):
                cells = [clean(cell.get_text(" ")) for cell in row.find_all(["td", "th"])]
                if any(cells):
                    rows.append(cells)
                    text = " | ".join(cells)
                    page.visible_chars += sum(len(cell) for cell in cells)
                    page.snippets.append(Snippet(text, "table", _zone(element), in_integration(element)))
            if rows:
                page.tables.append(rows)
            return
        if element.name == "address":
            lines = [clean(str(s)).strip(",") for s in element.find_all(string=True)]
            address = ", ".join(line for line in lines if line)
            if address:
                page.addresses.append(address)
                page.visible_chars += len(address)
                page.snippets.append(Snippet(address, "sentence", _zone(element), False))
            return
        if element.name in HEADINGS:
            emit_text([element], element, heading=True)
            return
        if not has_block_child(element):
            emit_text(list(element.children), element)
            return
        inline: list = []
        for child in list(element.children):
            if isinstance(child, Tag) and (child.name in BLOCK_TAGS or has_block_child(child)):
                emit_text(inline, element)
                inline = []
                visit(child)
            elif isinstance(child, (Tag, NavigableString)):
                inline.append(child)
        emit_text(inline, element)

    root = soup.body or soup
    visit(root)

    page.needs_rendering = page.visible_chars < config.min_visible_chars and (
        page.inline_script_chars >= INLINE_SCRIPT_SHELL_CHARS or page.external_scripts >= 1)
    return page
