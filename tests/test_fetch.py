"""Fetching: honest headers, robots, pacing, decoding, retries, blocked sites."""

import gzip
import zlib

import brotli
import pytest

from agent_scout import USER_AGENT, __version__
from agent_scout.fetch import DECODERS, Fetcher, looks_like_challenge

from conftest import html_page

OK_BODY = html_page("<h1>Hello</h1><p>" + "A real page with enough words. " * 20 + "</p>")


def test_user_agent_is_honest():
    assert USER_AGENT == f"agent-scout/{__version__} (+https://github.com/SamJ12138/agent-scout)"


def test_request_headers_and_only_decodable_encodings_are_advertised(scripted, make_fetcher):
    scripted.route("/", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "ok"
    for _, headers in scripted.hits:                      # robots.txt and the page
        assert headers["User-Agent"] == USER_AGENT
        advertised = [part.strip() for part in headers["Accept-Encoding"].split(",")]
        assert advertised == list(DECODERS)
    assert set(DECODERS) == {"gzip", "deflate", "br"}


def test_robots_is_fetched_once_per_origin_and_before_the_page(scripted, make_fetcher):
    scripted.route("/a", body=OK_BODY).route("/b", body=OK_BODY)
    fetcher = make_fetcher()
    fetcher.get(scripted.base + "/a")
    fetcher.get(scripted.base + "/b")
    assert scripted.paths() == ["/robots.txt", "/a", "/b"]     # robots 404 => allowed


def test_disallowed_url_is_not_requested(scripted, make_fetcher):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nDisallow: /secret\n")
    scripted.route("/secret", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/secret")
    assert (result.outcome, result.error_type) == ("robots_disallowed", "robots_disallowed")
    assert scripted.paths() == ["/robots.txt"]


def test_robots_5xx_disallows_everything_after_one_retry(scripted, make_fetcher):
    scripted.route("/robots.txt", status=500, body="oops").route("/", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("robots_disallowed", "robots_unreachable")
    assert scripted.paths() == ["/robots.txt", "/robots.txt"]


def test_robots_403_means_no_restrictions(scripted, make_fetcher):
    scripted.route("/robots.txt", status=403, body="no").route("/", body=OK_BODY)
    assert make_fetcher().get(scripted.base + "/").outcome == "ok"


def test_delay_between_requests_to_one_host(scripted, make_fetcher, fake_time):
    scripted.route("/a", body=OK_BODY).route("/b", body=OK_BODY)
    fetcher = make_fetcher(delay_seconds=1.5)
    fetcher.get(scripted.base + "/a")
    fetcher.get(scripted.base + "/b")
    # three requests (robots, /a, /b): a full delay before the second and the third
    assert fake_time.sleeps == [1.5, 1.5]


def test_crawl_delay_larger_than_config_wins(scripted, make_fetcher, fake_time):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nCrawl-delay: 4\n")
    scripted.route("/a", body=OK_BODY).route("/b", body=OK_BODY)
    fetcher = make_fetcher(delay_seconds=1.5)
    fetcher.get(scripted.base + "/a")
    fetcher.get(scripted.base + "/b")
    assert fake_time.sleeps == [4.0, 4.0]
    assert fetcher.delay_for(scripted.base + "/a") == 4.0


def test_crawl_delay_smaller_than_config_does_not_speed_us_up(scripted, make_fetcher, fake_time):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nCrawl-delay: 0.1\n")
    scripted.route("/a", body=OK_BODY)
    make_fetcher(delay_seconds=1.5).get(scripted.base + "/a")
    assert fake_time.sleeps == [1.5]


def test_crawl_delay_beyond_the_cap_skips_the_site(scripted, make_fetcher):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nCrawl-delay: 600\n")
    scripted.route("/", body=OK_BODY)
    result = make_fetcher(max_crawl_delay_seconds=30).get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("robots_disallowed", "crawl_delay_too_long")
    assert scripted.paths() == ["/robots.txt"]


@pytest.mark.parametrize("encoding, compress", [
    ("gzip", gzip.compress),
    ("deflate", zlib.compress),
    ("br", brotli.compress),
])
def test_compressed_bodies_are_decoded(scripted, make_fetcher, encoding, compress):
    scripted.route("/", headers={"Content-Encoding": encoding}, body=compress(OK_BODY.encode()))
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "ok"
    assert "A real page with enough words." in result.text
    assert result.content_encoding == encoding
    assert result.wire_bytes == len(compress(OK_BODY.encode()))


def test_unsupported_content_encoding_is_an_error_not_a_page(scripted, make_fetcher):
    scripted.route("/", headers={"Content-Encoding": "zstd"}, body=b"\x28\xb5\x2f\xfd binary")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("error", "unsupported_content_encoding", None)


def test_corrupt_compressed_body_is_an_error_not_a_page(scripted, make_fetcher):
    scripted.route("/", headers={"Content-Encoding": "br"}, body=b"this is not brotli at all")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("error", "undecodable_body", None)


def test_binary_body_without_encoding_header_is_an_error(scripted, make_fetcher):
    scripted.route("/", body=brotli.compress(OK_BODY.encode()))
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("error", "undecodable_text")


@pytest.mark.parametrize("header_charset, meta", [
    ("windows-1252", ""),
    (None, '<meta charset="windows-1252">'),
    (None, '<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'),
])
def test_non_utf8_charset_from_header_or_meta(scripted, make_fetcher, header_charset, meta):
    body = html_page("<p>Prices from £29 – “simple”.</p>", head=meta).encode("windows-1252")
    content_type = "text/html" + (f"; charset={header_charset}" if header_charset else "")
    scripted.route("/", headers={"Content-Type": content_type}, body=body)
    result = make_fetcher().get(scripted.base + "/")
    assert "Prices from £29 – “simple”." in result.text
    assert result.charset == "windows-1252"


def test_utf8_bom(scripted, make_fetcher):
    scripted.route("/", headers={"Content-Type": "text/html"}, body=b"\xef\xbb\xbf" + html_page("<p>café</p>").encode())
    result = make_fetcher().get(scripted.base + "/")
    assert "café" in result.text and not result.text.startswith("﻿")


def test_non_html_content_type_is_not_a_page(scripted, make_fetcher):
    scripted.route("/", headers={"Content-Type": "application/pdf"}, body=b"%PDF-1.7")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("error", "not_html")


def test_body_larger_than_limit_is_an_error(scripted, make_fetcher):
    scripted.route("/", body=OK_BODY + "x" * 5000)
    result = make_fetcher(max_body_bytes=2000).get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("error", "too_large")


def test_redirect_is_followed_and_recorded(scripted, make_fetcher):
    scripted.route("/old", status=301, headers={"Location": "/new"}).route("/new", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/old")
    assert result.outcome == "ok"
    assert result.final_url == scripted.base + "/new"
    assert result.redirects == [scripted.base + "/old"]


def test_redirect_target_is_checked_against_robots(scripted, make_fetcher):
    scripted.route("/robots.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nDisallow: /hidden\n")
    scripted.route("/old", status=302, headers={"Location": "/hidden"}).route("/hidden", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/old")
    assert result.outcome == "robots_disallowed"
    assert "/hidden" not in scripted.paths()


def test_redirect_loop_stops(scripted, make_fetcher):
    scripted.route("/a", status=302, headers={"Location": "/b"}).route("/b", status=302, headers={"Location": "/a"})
    result = make_fetcher().get(scripted.base + "/a")
    assert (result.outcome, result.error_type) == ("error", "too_many_redirects")


def test_one_retry_on_5xx_then_success(scripted, make_fetcher):
    scripted.route("/", status=503, body="busy").route("/", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "ok"
    assert scripted.paths().count("/") == 2


def test_5xx_twice_is_an_error_after_exactly_one_retry(scripted, make_fetcher):
    scripted.route("/", status=502, body="bad gateway")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.status) == ("error", "http_502", 502)
    assert scripted.paths().count("/") == 2


def test_429_is_retried_once_then_blocked(scripted, make_fetcher, fake_time):
    scripted.route("/", status=429, headers={"Retry-After": "3"}, body="slow down")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("blocked", "http_429")
    assert scripted.paths().count("/") == 2
    assert 3.0 in fake_time.sleeps          # Retry-After was honoured before the retry


@pytest.mark.parametrize("status", [401, 403])
def test_401_and_403_are_blocked_without_retry(scripted, make_fetcher, status):
    scripted.route("/", status=status, body="<h1>Access denied</h1>")
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("blocked", f"http_{status}", None)
    assert scripted.paths().count("/") == 1


def test_404_is_an_error(scripted, make_fetcher):
    result = make_fetcher().get(scripted.base + "/nothing")
    assert (result.outcome, result.error_type) == ("error", "http_404")


def test_challenge_page_with_status_200_is_blocked(scripted, make_fetcher):
    scripted.route("/", body=html_page("<p>Checking your browser before accessing the site.</p>", title="Just a moment..."))
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("blocked", "challenge_page", None)


def test_challenge_503_is_blocked_without_retry(scripted, make_fetcher):
    scripted.route("/", status=503, headers={"cf-mitigated": "challenge"}, body=html_page("<p>wait</p>", title="Just a moment..."))
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("blocked", "challenge_page")
    assert scripted.paths().count("/") == 1


@pytest.mark.parametrize("status, headers, text, expected", [
    (200, {}, html_page("<p>x</p>", title="Attention Required! | Cloudflare"), True),
    (200, {}, html_page("<p>How we handle access denied errors in our API</p>", title="Docs"), False),
    (200, {}, html_page("<p>x</p>", title="Pricing"), False),
    (503, {}, html_page("<p>maintenance</p>", title="Back soon"), False),
    (503, {}, "<html><script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></html>", True),
])
def test_looks_like_challenge(status, headers, text, expected):
    assert looks_like_challenge(status, headers, text) is expected


def test_timeout_is_an_error(scripted, make_fetcher):
    scripted.route("/", body=OK_BODY, delay=1.5)
    result = make_fetcher(timeout_seconds=0.3).get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("error", "timeout")


def test_connection_refused_is_an_error(make_fetcher):
    # robots.txt cannot be read either, which already rules the site out
    result = make_fetcher().get("http://127.0.0.1:9/")
    assert result.outcome == "robots_disallowed"
    assert result.error_type == "robots_unreachable"


def test_every_request_is_logged_with_url_status_bytes_encoding(scripted, make_fetcher, events):
    scripted.route("/", headers={"Content-Encoding": "gzip"}, body=gzip.compress(OK_BODY.encode()))
    make_fetcher().get(scripted.base + "/", site="s1")
    done = [e for e in events() if e["event"] != "start"]
    assert [(e["stage"], e["event"]) for e in done] == [("robots", "success"), ("fetch", "success")]
    fetch = done[1]
    assert fetch["site"] == "s1"
    assert fetch["context"]["url"] == scripted.base + "/"
    assert fetch["context"]["status"] == 200
    assert fetch["context"]["bytes"] > 0
    assert fetch["context"]["encoding"] == "gzip"
    assert isinstance(fetch["duration_ms"], int)


def test_failed_request_is_logged_with_error_type(scripted, make_fetcher, events):
    scripted.route("/", status=403, body="no")
    make_fetcher().get(scripted.base + "/", site="s1")
    fail = [e for e in events() if e["stage"] == "fetch" and e["event"] == "fail"]
    assert fail and fail[0]["error_type"] == "http_403"


def test_politeness_wait_is_logged_but_not_counted_as_request_time(scripted, make_fetcher, events):
    scripted.route("/a", body=OK_BODY)
    make_fetcher(delay_seconds=30).get(scripted.base + "/a", site="s1")      # fake clock: no real waiting
    fetch = [e for e in events() if e["stage"] == "fetch" and e["event"] == "success"][0]
    assert fetch["context"]["waited_ms"] == 30000
    assert fetch["duration_ms"] < 5000


def test_body_that_stalls_after_the_headers_is_a_timeout_not_a_crash(scripted, make_fetcher):
    scripted.route("/", headers={"X-Test-Stall-Body": "1.5"}, body=OK_BODY)
    result = make_fetcher(timeout_seconds=0.3).get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("error", "timeout", None)


def test_connection_closed_in_the_middle_of_the_body_is_a_read_error(scripted, make_fetcher):
    scripted.route("/", headers={"X-Test-Declared-Length": str(len(OK_BODY) + 500)}, body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type, result.text) == ("error", "read_error", None)


def test_malformed_redirect_target_is_an_error_not_a_crash(scripted, make_fetcher):
    scripted.route("/", status=302, headers={"Location": "http://[not-an-address/"})
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "error" and result.error_type in ("bad_redirect", "request_error")


# ------------------------------------------------------------------ redirects that carry a body
MOVED_BODY = ("<html>\r\n<head><title>301 Moved Permanently</title></head>\r\n<body>\r\n"
              "<center><h1>301 Moved Permanently</h1></center>\r\n<hr><center>server</center>\r\n</body>\r\n</html>\r\n")


def test_redirect_with_a_body_is_followed(scripted, make_fetcher):
    """Web servers send a small HTML page with their redirects by default."""
    scripted.route("/", status=301, headers={"Location": "/start"}, body=MOVED_BODY).route("/start", body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("ok", None)
    assert result.final_url == scripted.base + "/start" and "A real page with enough words." in result.text


def test_robots_redirect_with_a_body_is_followed(scripted, make_fetcher):
    scripted.route("/robots.txt", status=301, headers={"Location": "/robots-real.txt"}, body=MOVED_BODY)
    scripted.route("/robots-real.txt", headers={"Content-Type": "text/plain"}, body="User-agent: *\nDisallow: /secret\n")
    scripted.route("/", body=OK_BODY).route("/secret", body=OK_BODY)
    fetcher = make_fetcher()
    assert fetcher.get(scripted.base + "/").outcome == "ok"
    assert fetcher.get(scripted.base + "/secret").outcome == "robots_disallowed"   # the redirected file was read
    assert "/secret" not in scripted.paths()


@pytest.mark.parametrize("encoding, compress", [("gzip", gzip.compress), ("br", brotli.compress)])
def test_compressed_redirect_body_is_followed(scripted, make_fetcher, encoding, compress):
    scripted.route("/", status=302, headers={"Location": "/start", "Content-Encoding": encoding},
                   body=compress(MOVED_BODY.encode())).route("/start", body=OK_BODY)
    assert make_fetcher().get(scripted.base + "/").outcome == "ok"


# ------------------------------------------------------------------ header names in lower case
LOWER = {"X-Test-Lowercase-Names": "1"}


def test_lower_case_location_header_is_a_redirect_not_an_empty_page(scripted, make_fetcher):
    scripted.route("/", status=302, headers={**LOWER, "Location": "/start"})
    scripted.route("/start", headers={**LOWER, "Content-Type": "text/html; charset=utf-8"}, body=OK_BODY)
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "ok" and result.status == 200
    assert result.final_url == scripted.base + "/start" and result.redirects == [scripted.base + "/"]


def test_lower_case_content_encoding_and_content_type_are_honoured(scripted, make_fetcher):
    body = html_page("<p>Prices from £29 – “simple”.</p>").encode("windows-1252")
    scripted.route("/", headers={**LOWER, "Content-Type": "text/html; charset=windows-1252", "Content-Encoding": "br"},
                   body=brotli.compress(body))
    result = make_fetcher().get(scripted.base + "/")
    assert result.outcome == "ok" and "Prices from £29 – “simple”." in result.text
    assert (result.content_encoding, result.charset) == ("br", "windows-1252")


def test_lower_case_content_type_that_is_not_html_is_refused(scripted, make_fetcher):
    scripted.route("/", headers={**LOWER, "Content-Type": "application/pdf"}, body=b"%PDF-1.7")
    assert make_fetcher().get(scripted.base + "/").error_type == "not_html"


def test_lower_case_retry_after_and_content_length_are_honoured(scripted, make_fetcher, fake_time):
    scripted.route("/", status=429, headers={**LOWER, "Retry-After": "3"}, body="slow down")
    assert make_fetcher().get(scripted.base + "/").outcome == "blocked"
    assert 3.0 in fake_time.sleeps
    scripted.route("/cut", headers={**LOWER, "X-Test-Declared-Length": str(len(OK_BODY) + 500)}, body=OK_BODY)
    assert make_fetcher().get(scripted.base + "/cut").error_type == "read_error"


def test_lower_case_robots_redirect(scripted, make_fetcher):
    scripted.route("/robots.txt", status=302, headers={**LOWER, "Location": "/r.txt"})
    scripted.route("/r.txt", headers={**LOWER, "Content-Type": "text/plain"}, body="User-agent: *\nDisallow: /\n")
    scripted.route("/", body=OK_BODY)
    assert make_fetcher().get(scripted.base + "/").outcome == "robots_disallowed"


# ------------------------------------------------------------------ challenge pages: both directions
@pytest.mark.parametrize("title", [
    "Just a moment...", "Attention Required! | Cloudflare", "Access denied", "Access Denied | example.test",
    "Security check", "Are you a robot?", "Pardon Our Interruption", "Verify you are human",
])
def test_known_challenge_titles_are_blocked(scripted, make_fetcher, title):
    scripted.route("/", body=html_page("<p>Please wait while we check your browser.</p>", title=title))
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("blocked", "challenge_page")


@pytest.mark.parametrize("title", [
    "Security Checklist for Marketers | Wardenly",
    "reCAPTCHA alternative for lead forms - Formly",
    "Access Denied Errors Explained | Docs",
    "Human verification without friction: our product",
    "Pricing",
])
def test_ordinary_pages_whose_title_resembles_a_challenge_are_read(scripted, make_fetcher, title):
    scripted.route("/", body=html_page("<p>" + "An ordinary product page with words. " * 10 + "</p>", title=title))
    result = make_fetcher().get(scripted.base + "/")
    assert (result.outcome, result.error_type) == ("ok", None)


def test_loose_title_plus_challenge_markup_is_blocked():
    page = html_page("<script src='https://captcha-delivery.com/c.js'></script>", title="Site security check in progress")
    assert looks_like_challenge(200, {}, page) is True
    assert looks_like_challenge(200, {}, html_page("<p>x</p>", title="Site security check in progress")) is False
