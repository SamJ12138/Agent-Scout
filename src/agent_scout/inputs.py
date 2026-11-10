"""Read the list of sites to profile: a YAML file or a plain text file of URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from . import obs


class InputError(Exception):
    """The sites file cannot be used. The message is a single line."""


@dataclass(frozen=True)
class SiteInput:
    slug: str
    name: str | None
    url: str


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "site"


def _host_slug(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return slugify(host[4:] if host.startswith("www.") else host)


def _check_url(url: Any, where: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise InputError(f"{where}: missing url")
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InputError(f"{where}: not an http(s) URL: {url}")
    return url


def load_sites(path: Path) -> list[SiteInput]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        obs.emit("input", "fail", error_type="input_unreadable", path=str(path))
        raise InputError(f"cannot read sites file {path}: {exc.strerror or exc}") from None

    raw: list[tuple[str | None, str | None, Any, str]] = []   # slug, name, url, where
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            obs.emit("input", "fail", error_type="input_yaml", path=str(path))
            problem = getattr(exc, "problem", None) or "syntax error"
            raise InputError(f"sites file {path} is not valid YAML: {problem}") from None
        if isinstance(data, dict):
            data = data.get("sites")
        if not isinstance(data, list):
            raise InputError(f"sites file {path} must be a list of sites (or a mapping with a 'sites' list)")
        for index, item in enumerate(data, 1):
            where = f"{path.name} entry {index}"
            if isinstance(item, str):
                raw.append((None, None, item, where))
            elif isinstance(item, dict):
                name = item.get("name")
                slug = item.get("slug")
                raw.append((str(slug) if slug else None, str(name) if name else None, item.get("url"), where))
            else:
                raise InputError(f"{where}: expected a URL or a mapping with 'url'")
    else:
        for number, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if line and not line.startswith("#"):
                raw.append((None, None, line, f"{path.name} line {number}"))

    if not raw:
        raise InputError(f"sites file {path} lists no sites")

    sites: list[SiteInput] = []
    seen: dict[str, int] = {}
    for slug, name, url, where in raw:
        url = _check_url(url, where)
        base = slugify(slug) if slug else (slugify(name) if name else _host_slug(url))
        seen[base] = seen.get(base, 0) + 1
        final = base if seen[base] == 1 else f"{base}-{seen[base]}"
        sites.append(SiteInput(slug=final, name=name, url=url))
    return sites
