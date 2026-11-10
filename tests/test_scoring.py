"""Scoring results against ground truth: match / partial / mismatch / missing."""

import json

import pytest

from agent_scout import scoring
from agent_scout.model import FIELDS

U = "unknown"


@pytest.mark.parametrize("field, truth, got, outcome", [
    # both unknown is a match: the site does not say, and the tool did not claim
    ("can_execute", U, U, "match"),
    ("categories", U, U, "match"),
    ("categories", [], U, "match"),
    ("pricing", U, {"free_tier": U, "starting_price": U}, "match"),
    # reference known, tool silent
    ("can_execute", True, U, "missing"),
    ("integrations", ["Slack"], U, "missing"),
    ("pricing", {"free_tier": True, "starting_price": "$49/month"}, U, "missing"),
    # tool claims something the reference does not find on the site
    ("multi_agent", U, True, "mismatch"),
    ("tasks", U, ["write copy"], "mismatch"),
    # scalars are exact
    ("can_execute", True, True, "match"),
    ("can_execute", False, True, "mismatch"),
    ("can_execute", False, False, "match"),
    # lists compare as sets, ignoring case and order
    ("categories", ["seo", "advertising"], ["advertising", "seo"], "match"),
    ("integrations", ["HubSpot", "Slack"], ["slack", "hubspot"], "match"),
    ("categories", ["seo", "advertising"], ["seo"], "partial"),
    ("categories", ["seo"], ["seo", "ecommerce"], "partial"),
    ("categories", ["seo"], ["ecommerce"], "mismatch"),
    # one_liner: same text, or one contained in the other / mostly the same words
    ("one_liner", "An agent for ads.", "  an agent for ads ", "match"),
    ("one_liner", "Acme is an AI agent that plans and sends email campaigns.",
     "Acme is an AI agent that plans and sends email campaigns. Try it free today.", "partial"),
    ("one_liner", "An agent for ads.", "Cooking recipes for busy families.", "mismatch"),
    # pricing: two sub-values
    ("pricing", {"free_tier": True, "starting_price": "$49/month"},
     {"free_tier": True, "starting_price": "$49 per month"}, "match"),
    ("pricing", {"free_tier": True, "starting_price": "$49/month"},
     {"free_tier": True, "starting_price": "$49/mo"}, "match"),
    ("pricing", {"free_tier": True, "starting_price": "$49/month"},
     {"free_tier": True, "starting_price": U}, "partial"),
    ("pricing", {"free_tier": True, "starting_price": "$49/month"},
     {"free_tier": True, "starting_price": "$59/month"}, "partial"),
    ("pricing", {"free_tier": U, "starting_price": "$49/month"},
     {"free_tier": U, "starting_price": "$59/month"}, "mismatch"),     # agreeing on unknown earns nothing
    ("pricing", {"free_tier": U, "starting_price": "$49/month"},
     {"free_tier": True, "starting_price": "$49/month"}, "partial"),   # right price, unsupported free claim
    ("pricing", {"free_tier": True, "starting_price": U}, {"free_tier": True, "starting_price": U}, "match"),
    # headquarters
    ("hq_location", {"city": "Austin", "country": "United States"}, {"city": "austin", "country": "USA"}, "match"),
    ("hq_location", {"city": "Austin", "country": "United States"}, {"city": U, "country": "United States"}, "partial"),
    ("hq_location", {"city": "Austin", "country": "United States"}, {"city": "Dallas", "country": "United States"}, "partial"),
    ("hq_location", {"city": "Austin", "country": "United States"}, {"city": "Austin", "country": U}, "partial"),
    ("hq_location", {"city": "Austin", "country": "United States"}, {"city": "Paris", "country": "France"}, "mismatch"),
    ("hq_location", {"city": "Austin", "country": "United States"}, U, "missing"),
])
def test_compare(field, truth, got, outcome):
    assert scoring.compare(field, truth, got).outcome == outcome


@pytest.mark.parametrize("a, b", [
    ("$49/month", "$49 / mo"), ("$49/month", "$49 per month"), ("$49/month", "$49.00/month"),
    ("$1,200 a year", "$1200/yr"), ("£29 per month", "£29/month"), ("$20/user/month", "$20 per user per month"),
])
def test_price_normalisation_equates_spellings(a, b):
    assert scoring.normalise_price(a) == scoring.normalise_price(b)


def test_price_normalisation_keeps_real_differences():
    assert scoring.normalise_price("$49/month") != scoring.normalise_price("$49/year")
    assert scoring.normalise_price("$49/month") != scoring.normalise_price("€49/month")


def result_site(slug, values, status="ok", url="https://x.test/"):
    return {"slug": slug, "name": slug, "url": url, "status": status,
            "fields": {name: {"value": values.get(name, U), "evidence": []} for name in FIELDS}}


def truth_file(tmp_path, slug, values, url="https://x.test/", **extra):
    fields = {name: {"value": values.get(name, U)} for name in FIELDS}
    doc = {"slug": slug, "name": slug, "url": url, "fields": fields, **extra}
    (tmp_path / f"{slug}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_score_run_table_and_totals(tmp_path):
    truth_file(tmp_path, "a", {"can_execute": True, "categories": ["seo", "advertising"]})
    truth_file(tmp_path, "b", {"multi_agent": True})
    results = {"sites": [result_site("a", {"can_execute": True, "categories": ["seo"]}),
                         result_site("b", {}, status="blocked")]}
    score = scoring.score_results(results, tmp_path)
    assert score.sites["a"].outcomes["can_execute"].outcome == "match"
    assert score.sites["a"].outcomes["categories"].outcome == "partial"
    assert score.sites["b"].outcomes["multi_agent"].outcome == "missing"
    assert score.totals() == {"match": 16, "partial": 1, "mismatch": 0, "missing": 1}
    assert not score.all_match()
    text = score.table()
    assert "blocked" in text and "partial" in text and "missing" in text
    markdown = score.markdown()
    assert "| a |" in markdown and "| b |" in markdown


def test_sites_are_matched_by_slug_then_by_host(tmp_path):
    truth_file(tmp_path, "acme", {"can_execute": True}, url="https://www.acme.test/")
    results = {"sites": [result_site("acme-test", {"can_execute": True}, url="https://acme.test/home")]}
    score = scoring.score_results(results, tmp_path)
    assert list(score.sites) == ["acme"]
    assert score.all_match()


def test_missing_counterparts_are_reported_not_ignored(tmp_path):
    truth_file(tmp_path, "only-truth", {})
    results = {"sites": [result_site("only-result", {}, url="https://other.test/")]}
    score = scoring.score_results(results, tmp_path)
    assert score.unscored_results == ["only-result"]
    assert score.unscored_truth == ["only-truth"]
    assert not score.all_match()


def test_ground_truth_files_that_are_not_sites_are_skipped(tmp_path):
    (tmp_path / "notes.json").write_text('{"about": "not a site"}', encoding="utf-8")
    truth_file(tmp_path, "a", {})
    assert list(scoring.load_ground_truth(tmp_path)) == ["a"]


# ------------------------------------------------------------------ optional keys of real ground-truth files
def entry(value, **extra):
    return {"value": value, "source_url": "https://x.test/", "note": "ignored", "evidence": [{"item": "x"}],
            "kind": "meta description", "confidence": "low", **extra}


def test_unknown_keys_in_an_entry_are_ignored():
    assert scoring.compare_entry("can_execute", entry(True), True).outcome == "match"


def test_also_acceptable_one_liner():
    truth = entry("The meta description.", also_acceptable=["The hero headline. With its subhead."])
    assert scoring.compare_entry("one_liner", truth, "The hero headline. With its subhead.").outcome == "match"
    assert scoring.compare_entry("one_liner", truth, "Something else entirely here.").outcome == "mismatch"


@pytest.mark.parametrize("got_price, outcome", [
    ("$59/month", "match"),
    ("$69/month", "match"),            # listed in also_acceptable
    ("$79/month", "partial"),          # free_tier still right
    (U, "partial"),
])
def test_also_acceptable_prices_are_alternative_starting_prices(got_price, outcome):
    truth = entry({"free_tier": True, "starting_price": "$59/month"}, also_acceptable=["$69/month"])
    got = {"free_tier": True, "starting_price": got_price}
    assert scoring.compare_entry("pricing", truth, got).outcome == outcome


def test_also_acceptable_unknown_price():
    truth = entry({"free_tier": True, "starting_price": "$29/mo"}, also_acceptable=["$49/mo", "unknown"])
    assert scoring.compare_entry("pricing", truth, {"free_tier": True, "starting_price": U}).outcome == "match"


def test_country_not_printed_on_the_site_may_be_left_unknown():
    truth = entry({"city": "Paris", "country": "France"}, country_stated=False)
    assert scoring.compare_entry("hq_location", truth, {"city": "Paris", "country": U}).outcome == "match"
    assert scoring.compare_entry("hq_location", truth, {"city": "Paris", "country": "France"}).outcome == "match"
    assert scoring.compare_entry("hq_location", truth, {"city": "Paris", "country": "Spain"}).outcome == "partial"
    stated = entry({"city": "Paris", "country": "France"})
    assert scoring.compare_entry("hq_location", stated, {"city": "Paris", "country": U}).outcome == "partial"


@pytest.mark.parametrize("got, outcome", [
    (["Slack", "HubSpot"], "match"),
    (["Slack", "HubSpot", "Canva"], "match"),          # Canva is in overflow: neither required nor an error
    (["Slack", "Canva"], "partial"),
    (["Canva", "Zendesk"], "partial"),                 # only overflow names: right names, but not the listed ones
    (["Slack", "HubSpot", "Notion"], "partial"),       # Notion is a real extra
    (["Notion"], "mismatch"),
])
def test_integration_overflow_names_are_not_extras(got, outcome):
    truth = entry(["Slack", "HubSpot"], overflow=["Canva", "Zendesk"])
    assert scoring.compare_entry("integrations", truth, got).outcome == outcome


@pytest.mark.parametrize("a, b", [("42€/month", "€42/month"), ("42 €/month", "€42 per month"), ("29 EUR/month", "€29/mo"),
                                  ("USD 20/month", "$20/month")])
def test_price_normalisation_reads_trailing_and_spelled_currencies(a, b):
    assert scoring.normalise_price(a) == scoring.normalise_price(b)


def test_a_one_liner_of_punctuation_or_a_few_letters_is_not_a_partial_match():
    truth = "Zed is an ads agent for busy teams."
    assert scoring.compare("one_liner", truth, "...").outcome == "mismatch"
    assert scoring.compare("one_liner", truth, "Zed").outcome == "mismatch"
    assert scoring.compare("one_liner", truth, "Zed is an ads agent").outcome == "partial"


def test_country_spellings_are_compared_without_case():
    truth = {"city": "London", "country": "United Kingdom"}
    assert scoring.compare("hq_location", truth, {"city": "London", "country": "uk"}).outcome == "match"
    assert scoring.compare("hq_location", truth, {"city": "London", "country": "Great Britain"}).outcome == "match"
    assert scoring.compare("hq_location", truth, {"city": "London", "country": "us"}).outcome == "partial"
