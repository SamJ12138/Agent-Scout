"""robots.txt handling per RFC 9309."""

import pytest

from agent_scout.robots import RobotsPolicy, parse_robots, policy_for_response

BASIC = """
# comment
User-agent: *
Disallow: /private/
Allow: /private/press
Disallow: /*.pdf$
Crawl-delay: 2

Sitemap: https://example.com/sitemap.xml
"""


@pytest.mark.parametrize("path, allowed", [
    ("/", True),
    ("/pricing", True),
    ("/private/", False),
    ("/private/notes", False),
    ("/private/press", True),            # longer Allow beats shorter Disallow
    ("/private/press/2026", True),
    ("/files/a.pdf", False),             # * and $ wildcards
    ("/files/a.pdf?download=1", True),   # $ anchors the end
    ("/robots.txt", True),               # always fetchable
])
def test_longest_match_and_wildcards(path, allowed):
    policy = parse_robots(BASIC)
    assert policy.allows(path) is allowed
    assert policy.crawl_delay == 2.0


def test_allow_wins_a_tie():
    policy = parse_robots("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert policy.allows("/page") is True


def test_empty_disallow_allows_everything():
    assert parse_robots("User-agent: *\nDisallow:\n").allows("/anything") is True


def test_specific_group_replaces_the_star_group():
    text = ("User-agent: *\nDisallow: /\n\n"
            "User-agent: Agent-Scout\nCrawl-delay: 0.5\nDisallow: /drafts/\n")
    policy = parse_robots(text)
    assert policy.allows("/") is True
    assert policy.allows("/drafts/x") is False
    assert policy.crawl_delay == 0.5


def test_star_group_used_when_no_group_names_us():
    policy = parse_robots("User-agent: otherbot\nDisallow: /\n\nUser-agent: *\nDisallow: /a\n")
    assert policy.allows("/b") is True
    assert policy.allows("/a") is False


def test_no_matching_group_at_all_allows():
    assert parse_robots("User-agent: otherbot\nDisallow: /\n").allows("/") is True


def test_several_user_agent_lines_share_one_group_and_groups_merge():
    text = ("User-agent: otherbot\nUser-agent: agent-scout\nDisallow: /a\n\n"
            "User-agent: agent-scout\nDisallow: /b\n")
    policy = parse_robots(text)
    assert not policy.allows("/a") and not policy.allows("/b") and policy.allows("/c")


def test_product_token_must_match_whole_token():
    # "agent-scout-pro" is a different crawler
    policy = parse_robots("User-agent: agent-scout-pro\nDisallow: /\n\nUser-agent: *\nDisallow: /x\n")
    assert policy.allows("/") is True


def test_percent_encoding_is_normalised():
    policy = parse_robots("User-agent: *\nDisallow: /caf%c3%a9/\nDisallow: /a%7Eb\n")
    assert policy.allows("/caf%C3%A9/menu") is False
    assert policy.allows("/a~b") is False


def test_query_string_is_part_of_the_match():
    policy = parse_robots("User-agent: *\nDisallow: /search?q=\n")
    assert policy.allows("/search?q=x") is False
    assert policy.allows("/search") is True


def test_bom_crlf_and_junk_lines():
    text = "﻿User-agent: *\r\nDisallow: /x\r\nthis line has no colon\r\nCrawl-delay: soon\r\n"
    policy = parse_robots(text)
    assert policy.allows("/x") is False
    assert policy.crawl_delay is None


@pytest.mark.parametrize("status, allowed, state", [
    (200, True, "ok"),
    (404, True, "missing"),      # 4xx: no restrictions
    (403, True, "missing"),
    (410, True, "missing"),
    (500, False, "unreachable"), # 5xx: assume complete disallow for this run
    (503, False, "unreachable"),
    (None, False, "unreachable"),  # network error
])
def test_status_code_policy(status, allowed, state):
    policy = policy_for_response(status, "User-agent: *\nDisallow: /nothing\n")
    assert policy.allows("/") is allowed
    assert policy.state == state
    assert policy.http_status == status


def test_policy_helpers():
    assert RobotsPolicy.allow_all("missing", 404).allows("/x")
    assert not RobotsPolicy.disallow_all("unreachable", 500).allows("/x")
    assert RobotsPolicy.disallow_all("unreachable", 500).allows("/robots.txt")
