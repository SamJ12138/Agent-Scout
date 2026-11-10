"""robots.txt per RFC 9309.

- The group that names our product token (``agent-scout``, case-insensitive)
  is used; several such groups are merged. Without one, the ``*`` group applies.
- Allow/Disallow paths may contain ``*`` and a trailing ``$``. The longest
  matching pattern wins; Allow wins a tie; no match means allowed.
- /robots.txt itself is always fetchable.
- Status handling (section 2.3.1): 2xx parse; 4xx "unavailable" means no
  restrictions; 5xx or a network failure "unreachable" means the whole site is
  disallowed for this run.
- ``Crawl-delay`` is not part of the RFC but is honoured when present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import obs

PRODUCT_TOKEN = "agent-scout"
MAX_ROBOTS_CHARS = 500 * 1024   # RFC 9309 asks parsers to handle at least 500 KiB

_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"


def _normalise(path: str) -> str:
    """Upper-case percent-escapes and decode the ones for unreserved characters."""
    def replace(match: re.Match) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()
    return re.sub(r"%([0-9A-Fa-f]{2})", replace, path)


def _pattern_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""), re.DOTALL)


@dataclass
class Rule:
    allow: bool
    pattern: str
    regex: re.Pattern = field(repr=False, compare=False, default=None)  # type: ignore[assignment]

    def __post_init__(self):
        self.regex = _pattern_regex(self.pattern)


@dataclass
class RobotsPolicy:
    state: str                       # ok | missing | unreachable
    http_status: int | None = None
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None
    blanket: bool | None = None      # True: allow all, False: disallow all, None: use rules

    @classmethod
    def allow_all(cls, state: str, http_status: int | None) -> "RobotsPolicy":
        return cls(state=state, http_status=http_status, blanket=True)

    @classmethod
    def disallow_all(cls, state: str, http_status: int | None) -> "RobotsPolicy":
        return cls(state=state, http_status=http_status, blanket=False)

    def allows(self, path: str) -> bool:
        """``path`` is the URL path plus ``?query`` when there is one."""
        if path.split("?")[0] == "/robots.txt":
            return True
        if self.blanket is not None:
            return self.blanket
        path = _normalise(path or "/")
        best_length, best_allow = -1, True
        for rule in self.rules:
            if rule.regex.match(path):
                length = len(rule.pattern.encode("utf-8"))
                if length > best_length or (length == best_length and rule.allow):
                    best_length, best_allow = length, rule.allow
        return best_allow


def _token(value: str) -> str:
    match = re.match(r"[A-Za-z_-]+|\*", value.strip())
    return match.group(0).lower() if match else ""


def parse_robots(text: str, http_status: int | None = 200) -> RobotsPolicy:
    groups: list[dict] = []
    current: dict | None = None
    expecting_agents = False      # consecutive User-agent lines share a group
    for raw in text[:MAX_ROBOTS_CHARS].lstrip("﻿").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not expecting_agents or current is None:
                current = {"agents": [], "rules": [], "crawl_delay": None}
                groups.append(current)
            current["agents"].append(_token(value))
            expecting_agents = True
            continue
        if key in ("allow", "disallow", "crawl-delay"):
            expecting_agents = False
            if current is None:
                continue                      # rule before any User-agent line
            if key == "crawl-delay":
                if re.fullmatch(r"\d+(\.\d+)?", value):
                    current["crawl_delay"] = float(value)
            elif value:                       # an empty Disallow matches nothing
                pattern = _normalise(value if value.startswith(("/", "*")) else "/" + value)
                current["rules"].append(Rule(allow=(key == "allow"), pattern=pattern))

    chosen = [g for g in groups if PRODUCT_TOKEN in g["agents"]] or [g for g in groups if "*" in g["agents"]]
    policy = RobotsPolicy(state="ok", http_status=http_status)
    for group in chosen:
        policy.rules.extend(group["rules"])
        if group["crawl_delay"] is not None:
            policy.crawl_delay = max(policy.crawl_delay or 0.0, group["crawl_delay"])
    return policy


def policy_for_response(status: int | None, text: str | None) -> RobotsPolicy:
    """Turn the outcome of fetching /robots.txt into a policy."""
    if status is None or status >= 500:
        obs.emit("robots", "skip", error_type="robots_unreachable", status=status)
        return RobotsPolicy.disallow_all("unreachable", status)
    if 200 <= status < 300:
        return parse_robots(text or "", status)
    return RobotsPolicy.allow_all("missing", status)
