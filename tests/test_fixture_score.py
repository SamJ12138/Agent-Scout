"""The regression gate: on the bundled fictional sites, with default settings
apart from the delay, the tool must match the ground truth on every field."""

import json

import pytest

from agent_scout import scoring
from agent_scout.cli import main
from agent_scout.model import FIELDS, UNKNOWN
from fixture_server import GROUND_TRUTH_DIR


@pytest.fixture(scope="session")
def fixture_run(fixture_sites, tmp_path_factory):
    work = tmp_path_factory.mktemp("fixture-run")
    sites = work / "sites.yaml"
    sites.write_text(fixture_sites.sites_yaml(), encoding="utf-8")
    code = main(["run", str(sites), "-o", str(work / "out"), "--log-dir", str(work / "logs"),
                 "--delay", "0", "--quiet"])
    assert code == 0
    results = json.loads((work / "out" / "results.json").read_text(encoding="utf-8"))
    return work, results


def test_every_field_of_every_fixture_site_matches(fixture_run):
    _, results = fixture_run
    score = scoring.score_results(results, GROUND_TRUTH_DIR)
    assert score.all_match(), "\n" + score.table()
    assert score.totals()["match"] == 6 * len(FIELDS)


def test_site_statuses(fixture_run):
    _, results = fixture_run
    assert {site["slug"]: site["status"] for site in results["sites"]} == {
        "glimmer": "partial", "northwind": "ok", "orbitfleet": "ok",
        "palisade": "blocked", "quillmate": "ok", "tessera": "robots_disallowed"}
    glimmer = next(site for site in results["sites"] if site["slug"] == "glimmer")
    assert glimmer["needs_rendering"] is True


def test_blocked_and_disallowed_sites_have_every_field_unknown_and_no_evidence(fixture_run):
    _, results = fixture_run
    for site in results["sites"]:
        if site["status"] in ("blocked", "robots_disallowed", "unreachable"):
            for name in FIELDS:
                assert site["fields"][name] == {"value": UNKNOWN, "evidence": []}, (site["slug"], name)


def test_every_known_value_has_evidence_that_is_on_the_page(fixture_run, fixture_sites):
    """Each quote must be findable in the page it cites (served by the fixture server)."""
    import requests
    from agent_scout.config import Config
    from agent_scout.page import parse_page
    from agent_scout.textmatch import normalise_for_quote
    _, results = fixture_run
    cache = {}
    checked = 0
    for site in results["sites"]:
        for name, field in site["fields"].items():
            if field["value"] == UNKNOWN:
                continue
            assert field["evidence"], (site["slug"], name)
            for evidence in field["evidence"]:
                assert evidence["method"] in ("meta", "json-ld", "heading", "sentence", "link", "table")
                if evidence["url"] not in cache:
                    response = requests.get(evidence["url"], timeout=5)
                    response.encoding = response.apparent_encoding if "charset" not in response.headers.get(
                        "Content-Type", "") else response.encoding
                    cache[evidence["url"]] = response.text
                html = cache[evidence["url"]]
                if evidence["method"] == "json-ld":
                    assert json.loads(evidence["quote"])           # a JSON fragment of the page's JSON-LD
                    continue
                page_text = normalise_for_quote(parse_page(evidence["url"], html, Config()).text())
                for part in evidence["quote"].split(" | "):
                    assert normalise_for_quote(part) in page_text, (site["slug"], name, evidence["quote"])
                checked += 1
    assert checked > 30


def test_results_json_schema(fixture_run):
    _, results = fixture_run
    assert results["schema_version"] == "1.0"
    assert set(results) == {"schema_version", "tool", "run_id", "started_at", "finished_at", "settings", "sites"}
    site = results["sites"][0]
    assert set(site) == {"slug", "name", "url", "final_url", "status", "status_detail", "needs_rendering",
                         "robots", "pages", "fields", "llm"}
    assert set(site["fields"]) == set(FIELDS)
    for page in site["pages"]:
        assert set(page) == {"url", "final_url", "topic", "outcome", "http_status", "error_type", "bytes",
                             "encoding", "charset"}


def test_run_log_covers_every_stage(fixture_run):
    work, results = fixture_run
    logs = list((work / "logs").glob("run_*.jsonl"))
    assert len(logs) == 1 and results["run_id"] in logs[0].name
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert {"input", "robots", "fetch", "parse", "extract", "report", "run"} <= {e["stage"] for e in events}
    assert all(e["run_id"] == results["run_id"] for e in events)
    blocked = [e for e in events if e["site"] == "palisade" and e["event"] == "fail"]
    assert any(e["error_type"] == "http_403" for e in blocked)
