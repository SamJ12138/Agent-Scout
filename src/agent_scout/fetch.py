"""Polite HTTP fetching.

One ``Fetcher`` is used for a whole run. For every URL it

1. reads the origin's robots.txt (once) and refuses URLs it disallows;
2. waits so that two requests to the same host are at least
   max(config delay, Crawl-delay) apart;
3. sends an honest User-Agent and advertises only the content encodings in
   ``DECODERS``, then decodes the body itself: a body that cannot be decoded is
   an error, never a page;
4. follows up to five redirects, checking robots.txt for every hop;
5. retries once on 5xx or 429;
6. reports 401 / 403 / 429 / a challenge page as ``blocked`` and stops there.
   Nothing here tries to get around bot protection.
"""

from __future__ import annotations

import codecs
import gzip
import re
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit

import brotli
import requests

from . import USER_AGENT, obs
from .config import Config
from .robots import RobotsPolicy, policy_for_response

MAX_REDIRECTS = 5
MAX_RETRY_AFTER_SECONDS = 30.0


def _inflate(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except zlib.error:
        obs.emit("fetch", "skip", error_type="deflate_raw_stream")
        return zlib.decompress(data, -zlib.MAX_WBITS)   # some servers send a raw stream


# Content encodings this tool can decode. The Accept-Encoding request header is
# built from these keys and nothing else.
DECODERS: dict[str, Callable[[bytes], bytes]] = {
    "gzip": gzip.decompress,
    "deflate": _inflate,
    "br": brotli.decompress,
}

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5,*/*;q=0.1",
    "Accept-Encoding": ", ".join(DECODERS),
    "Accept-Language": "en",
}

BLOCKED_STATUSES = (401, 403, 429)

# Page titles used by bot-protection interstitials (compared lower-case).
CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "are you a robot",
    "pardon our interruption",
    "security check",
    "captcha",
    "verify you are human",
    "human verification",
)
# Markup that only appears on challenge pages.
CHALLENGE_MARKUP = (
    "/cdn-cgi/challenge-platform",
    "cf-chl-",
    "captcha-delivery.com",
    "px-captcha",
    "_incapsula_resource",
)


def looks_like_challenge(status: int, headers: dict, text: str) -> bool:
    """True when a response is a bot-protection challenge rather than content.

    For a 200 response only the page title counts: ordinary pages served
    through a CDN may reference its challenge scripts.
    """
    lowered = {str(k).lower(): str(v).lower() for k, v in headers.items()}
    if lowered.get("cf-mitigated") == "challenge":
        return True
    head = text[:20000].lower()
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.DOTALL)
    if title and any(marker in title.group(1) for marker in CHALLENGE_TITLES):
        return True
    return status != 200 and any(marker in head for marker in CHALLENGE_MARKUP)


@dataclass
class FetchResult:
    url: str                              # URL asked for
    final_url: str                        # URL that answered (after redirects)
    outcome: str                          # ok | robots_disallowed | blocked | error
    error_type: str | None = None
    status: int | None = None
    text: str | None = None               # decoded HTML, only when outcome == "ok"
    wire_bytes: int = 0                   # body bytes as received
    content_encoding: str | None = None
    charset: str | None = None
    redirects: list[str] = field(default_factory=list)


REDIRECT_STATUSES = (301, 302, 303, 307, 308)


@dataclass
class _Response:
    status: int | None = None
    headers: dict = field(default_factory=dict)
    body: bytes = b""                     # decoded (decompressed) body
    encoding: str | None = None
    error: str | None = None              # set when the request or the decoding failed
    wire_bytes: int = 0

    def preview(self) -> str:
        return self.body[:20000].decode("utf-8", errors="replace")


class _Failure(Exception):
    def __init__(self, error_type: str):
        super().__init__(error_type)
        self.error_type = error_type


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _path_query(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def sniff_charset(content_type: str, body: bytes) -> str:
    match = re.search(r"charset=[\"']?([\w.:-]+)", content_type or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    if body.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    head = body[:4096].decode("ascii", errors="replace")
    match = re.search(r"<meta[^>]+charset=[\"']?\s*([\w.:-]+)", head, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return "utf-8"


def decode_text(body: bytes, charset: str) -> tuple[str, str]:
    """Decode HTML bytes. Raises _Failure when the result is not text."""
    try:
        codecs.lookup(charset)
    except LookupError:
        obs.emit("fetch", "skip", error_type="unknown_charset", charset=charset)
        charset = "utf-8"
    try:
        text = body.decode(charset)
    except UnicodeDecodeError:
        obs.emit("fetch", "skip", error_type="charset_mismatch", charset=charset)
        text = body.decode(charset, errors="replace")
        if text.count("�") > max(5, len(text) // 1000):
            raise _Failure("undecodable_text") from None
    if "\x00" in text[:2048]:
        raise _Failure("undecodable_text")
    return text.lstrip("﻿"), ("utf-8" if charset == "utf-8-sig" else charset)


class Fetcher:
    def __init__(self, config: Config, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, RobotsPolicy] = {}
        self._last_request: dict[str, float] = {}
        self._extra_wait: dict[str, float] = {}

    # ------------------------------------------------------------------ pacing
    def delay_for(self, url: str) -> float:
        policy = self._robots.get(_origin(url))
        crawl_delay = policy.crawl_delay if policy and policy.crawl_delay else 0.0
        return max(self.config.delay_seconds, crawl_delay)

    def _pace(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            gap = max(self.delay_for(url), self._extra_wait.pop(host, 0.0))
            wait = last + gap - self._clock()
            if wait > 0:
                self._sleep(wait)

    # ------------------------------------------------------------------ one request
    def _request(self, url: str) -> tuple[int, dict, bytes]:
        """One GET without redirects. Returns status, headers, raw body bytes."""
        self._pace(url)
        try:
            response = self.session.get(url, headers=REQUEST_HEADERS, timeout=self.config.timeout_seconds,
                                        allow_redirects=False, stream=True)
            try:
                body = response.raw.read(self.config.max_body_bytes + 1, decode_content=False)
            finally:
                response.close()
        except requests.exceptions.Timeout:
            obs.emit("fetch", "skip", error_type="timeout", url=url)
            raise _Failure("timeout") from None
        except requests.exceptions.SSLError:
            obs.emit("fetch", "skip", error_type="tls_error", url=url)
            raise _Failure("tls_error") from None
        except requests.exceptions.ConnectionError:
            obs.emit("fetch", "skip", error_type="connection_error", url=url)
            raise _Failure("connection_error") from None
        except (requests.exceptions.RequestException, OSError) as exc:
            obs.emit("fetch", "skip", error_type="request_error", url=url, detail=type(exc).__name__)
            raise _Failure("request_error") from None
        finally:
            self._last_request[urlsplit(url).netloc] = self._clock()
        return response.status_code, dict(response.headers), body

    def _decoded_body(self, headers: dict, body: bytes) -> tuple[bytes, str | None]:
        if len(body) > self.config.max_body_bytes:
            raise _Failure("too_large")
        header = (headers.get("Content-Encoding") or "").strip().lower()
        encodings = [part.strip() for part in header.split(",") if part.strip() and part.strip() != "identity"]
        for encoding in reversed(encodings):
            if encoding not in DECODERS:
                raise _Failure("unsupported_content_encoding")
            try:
                body = DECODERS[encoding](body)
            except Exception as exc:   # each decoder raises its own error type
                obs.emit("fetch", "skip", error_type="undecodable_body", encoding=encoding,
                         detail=type(exc).__name__)
                raise _Failure("undecodable_body") from None
            if len(body) > self.config.max_body_bytes:
                raise _Failure("too_large")
        return body, (", ".join(encodings) or None)

    def _retry_after(self, headers: dict) -> float:
        value = str(headers.get("Retry-After", "")).strip()
        return min(float(value), MAX_RETRY_AFTER_SECONDS) if value.isdigit() else 0.0

    def _attempt(self, url: str, stage: str, site: str | None, missing_ok: bool = False) -> "_Response":
        """GET with one retry on 5xx/429; each attempt is one logged span.

        ``missing_ok``: a 4xx answer is a normal outcome (robots.txt absent).
        """
        for attempt in (1, 2):
            with obs.span(stage, site=site, url=url, attempt=attempt) as span:
                try:
                    status, headers, raw = self._request(url)
                except _Failure as failure:
                    span.fail(failure.error_type)
                    return _Response(error=failure.error_type)
                span.context.update(status=status, bytes=len(raw),
                                    encoding=headers.get("Content-Encoding") or "identity")
                response = _Response(status=status, headers=headers, wire_bytes=len(raw))
                try:
                    response.body, response.encoding = self._decoded_body(headers, raw)
                except _Failure as failure:
                    response.error = failure.error_type
                    span.fail(failure.error_type)
                    return response
                retry = attempt == 1 and (status >= 500 or status == 429)
                if retry and status != 429 and looks_like_challenge(status, headers, response.preview()):
                    retry = False                     # a challenge page is not retried
                if status >= 500 or (status >= 400 and not missing_ok):
                    span.fail(f"http_{status}", will_retry=retry)
            if not retry:
                return response
            self._extra_wait[urlsplit(url).netloc] = self._retry_after(headers)
        raise AssertionError("unreachable")   # pragma: no cover

    # ------------------------------------------------------------------ robots
    def robots_for(self, url: str, site: str | None = None) -> RobotsPolicy:
        origin = _origin(url)
        if origin in self._robots:
            return self._robots[origin]
        robots_url = origin + "/robots.txt"
        status: int | None = None
        text: str | None = None
        for _ in range(MAX_REDIRECTS + 1):
            response = self._attempt(robots_url, "robots", site, missing_ok=True)
            status = None if response.error else response.status
            location = response.headers.get("Location")
            if status in REDIRECT_STATUSES and location:
                robots_url = urljoin(robots_url, location)
                status = None                 # stays None if the redirects never end
                continue
            if status is not None and 200 <= status < 300:
                text = response.body.decode("utf-8", errors="replace")
            break
        policy = policy_for_response(status, text)
        self._robots[origin] = policy
        return policy

    # ------------------------------------------------------------------ pages
    def get(self, url: str, site: str | None = None) -> FetchResult:
        """Fetch one HTML page, honouring robots.txt on every redirect hop."""
        asked = url
        hops: list[str] = []
        for _ in range(MAX_REDIRECTS + 1):
            policy = self.robots_for(url, site)
            if policy.crawl_delay and policy.crawl_delay > self.config.max_crawl_delay_seconds:
                obs.emit("fetch", "skip", site=site, error_type="crawl_delay_too_long", url=url,
                         crawl_delay=policy.crawl_delay)
                return FetchResult(asked, url, "robots_disallowed", "crawl_delay_too_long", redirects=hops)
            if not policy.allows(_path_query(url)):
                reason = "robots_unreachable" if policy.state == "unreachable" else "robots_disallowed"
                obs.emit("fetch", "skip", site=site, error_type=reason, url=url)
                return FetchResult(asked, url, "robots_disallowed", reason, status=policy.http_status,
                                   redirects=hops)

            response = self._attempt(url, "fetch", site)
            status, headers = response.status, response.headers
            base = dict(url=asked, final_url=url, status=status, wire_bytes=response.wire_bytes, redirects=hops)
            if status in BLOCKED_STATUSES:
                return FetchResult(outcome="blocked", error_type=f"http_{status}", **base)
            if response.error is not None:
                return FetchResult(outcome="error", error_type=response.error, **base)
            location = headers.get("Location")
            if status in REDIRECT_STATUSES and location:
                hops.append(url)
                url = urljoin(url, location).split("#")[0]
                continue
            if looks_like_challenge(status, headers, response.preview()):
                obs.emit("fetch", "fail", site=site, error_type="challenge_page", url=url, status=status)
                return FetchResult(outcome="blocked", error_type="challenge_page", **base)
            if status >= 400:
                return FetchResult(outcome="error", error_type=f"http_{status}", **base)

            content_type = headers.get("Content-Type", "")
            if content_type and not re.match(r"\s*(text/html|application/xhtml\+xml)", content_type, re.IGNORECASE):
                obs.emit("fetch", "fail", site=site, error_type="not_html", url=url, content_type=content_type)
                return FetchResult(outcome="error", error_type="not_html", **base)
            try:
                text, charset = decode_text(response.body, sniff_charset(content_type, response.body))
            except _Failure as failure:
                obs.emit("fetch", "fail", site=site, error_type=failure.error_type, url=url)
                return FetchResult(outcome="error", error_type=failure.error_type, **base)
            return FetchResult(outcome="ok", text=text, content_encoding=response.encoding, charset=charset, **base)

        obs.emit("fetch", "fail", site=site, error_type="too_many_redirects", url=asked)
        return FetchResult(asked, url, "error", "too_many_redirects", redirects=hops)
