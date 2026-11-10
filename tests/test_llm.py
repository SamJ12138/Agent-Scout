"""The optional LLM pass, tested against a fake transport.

There is no API key in the test environment and nothing here opens a network
connection: every request goes to FakeTransport.
"""

import json

import pytest
import requests

from agent_scout import llm
from agent_scout.config import Config, LLMConfig
from agent_scout.model import FIELDS, UNKNOWN, FieldResult
from agent_scout.page import parse_page

from conftest import html_page

KEY = "sk-TEST-0123456789-SECRET"
PAGE_HTML = html_page(
    "<h1>Acme Agent</h1><p>Acme sends each email campaign automatically. Built for agencies and  online stores.</p>"
    "<p>Plans start at $29/month. Acme integrates with Fernleaf CRM.</p>"
    "<p>We are headquartered in Lisbon, Portugal.</p>"
    "<p>" + "More ordinary words on the page. " * 8 + "</p>",
    title="Acme Agent", head='<meta name="description" content="Acme is an email agent.">')


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, text=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeTransport:
    """Stands in for requests.Session: records calls and replays scripted answers."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def openai_answer(content):
    return FakeResponse(payload={"choices": [{"message": {"role": "assistant", "content": content}}]})


def anthropic_answer(content):
    return FakeResponse(payload={"content": [{"type": "text", "text": content}], "stop_reason": "end_turn"})


def settings(provider="openai-compatible", base_url="https://llm.test/v1"):
    return llm.LLMSettings(provider=provider, base_url=base_url, model="test-model", api_key=KEY,
                           timeout_seconds=30, max_chars_per_site=24000)


def client(transport, sleeps=None, **kwargs):
    return llm.LLMClient(settings(**kwargs), transport=transport, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def pages():
    return [parse_page("https://acme.test/", PAGE_HTML, Config())]


def site_result(**known):
    fields = {name: FieldResult().as_dict() for name in FIELDS}
    fields.update(known)
    return {"slug": "acme", "name": "Acme", "status": "ok", "fields": fields, "llm": None}


GOOD = {
    "categories": [{"value": "email marketing", "quote": "Acme sends each email campaign automatically."}],
    "target_user": [{"value": "agencies", "quote": "Built for agencies and online stores."},
                    {"value": "ecommerce brands", "quote": "Built for agencies and online stores."}],
    "tasks": [{"value": "send email campaigns", "quote": "Acme sends each email campaign automatically."}],
    "can_execute": {"value": True, "quote": "Acme sends each email campaign automatically."},
    "multi_agent": None,
    "integrations": [{"value": "Fernleaf CRM", "quote": "Acme integrates with Fernleaf CRM."}],
    "pricing": {"free_tier": None, "starting_price": {"value": "$29/month", "quote": "Plans start at $29/month."}},
    "hq_location": {"city": "Lisbon", "country": "Portugal", "quote": "We are headquartered in Lisbon, Portugal."},
    "one_liner": {"value": "Acme is an email agent.", "quote": "Acme is an email agent."},
}


# ------------------------------------------------------------------ transport and providers
def test_openai_compatible_request_shape():
    transport = FakeTransport(openai_answer("{}"))
    assert client(transport).complete("SYSTEM", "USER") == "{}"
    call = transport.calls[0]
    assert call["url"] == "https://llm.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["model"] == "test-model"
    assert call["json"]["messages"] == [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "USER"}]
    assert call["timeout"] == 30


def test_anthropic_request_shape():
    transport = FakeTransport(anthropic_answer("{}"))
    assert client(transport, provider="anthropic", base_url=None).complete("SYSTEM", "USER") == "{}"
    call = transport.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == KEY and call["headers"]["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in call["headers"]
    assert call["json"]["system"] == "SYSTEM"
    assert call["json"]["messages"] == [{"role": "user", "content": "USER"}]
    assert call["json"]["max_tokens"] > 0


def test_401_is_an_auth_error_without_retry_and_without_the_key():
    transport = FakeTransport(FakeResponse(status=401, payload={"error": {"message": f"bad key {KEY}"}}))
    with pytest.raises(llm.LLMError) as err:
        client(transport).complete("s", "u")
    assert err.value.error_type == "auth"
    assert len(transport.calls) == 1
    assert KEY not in str(err.value) and KEY not in repr(err.value)


def test_429_is_retried_once_then_succeeds():
    sleeps = []
    transport = FakeTransport(FakeResponse(status=429, payload={}, headers={"Retry-After": "2"}), openai_answer("{}"))
    assert client(transport, sleeps).complete("s", "u") == "{}"
    assert len(transport.calls) == 2 and sleeps == [2.0]


def test_429_twice_is_rate_limited_after_exactly_one_retry():
    sleeps = []
    transport = FakeTransport(FakeResponse(status=429, payload={}))
    with pytest.raises(llm.LLMError) as err:
        client(transport, sleeps).complete("s", "u")
    assert err.value.error_type == "rate_limited"
    assert len(transport.calls) == 2 and len(sleeps) == 1


def test_timeout_and_connection_errors():
    with pytest.raises(llm.LLMError) as err:
        client(FakeTransport(requests.exceptions.Timeout("slow"))).complete("s", "u")
    assert err.value.error_type == "timeout"
    with pytest.raises(llm.LLMError) as err:
        client(FakeTransport(requests.exceptions.ConnectionError(f"refused {KEY}"))).complete("s", "u")
    assert err.value.error_type == "connection_error" and KEY not in str(err.value)


def test_server_error_and_unexpected_payload():
    with pytest.raises(llm.LLMError) as err:
        client(FakeTransport(FakeResponse(status=500, payload={}))).complete("s", "u")
    assert err.value.error_type == "http_500"
    with pytest.raises(llm.LLMError) as err:
        client(FakeTransport(FakeResponse(payload={"unexpected": True}))).complete("s", "u")
    assert err.value.error_type == "bad_response"
    with pytest.raises(llm.LLMError) as err:
        client(FakeTransport(FakeResponse(payload=None, text="<html>gateway</html>"))).complete("s", "u")
    assert err.value.error_type == "bad_response"


def test_anthropic_version_header_is_a_setting():
    transport = FakeTransport(anthropic_answer("{}"))
    custom = settings(provider="anthropic", base_url=None)
    custom.anthropic_version = "2026-10-21"
    llm.LLMClient(custom, transport=transport).complete("s", "u")
    assert transport.calls[0]["headers"]["anthropic-version"] == "2026-10-21"


# ------------------------------------------------------------------ prompt
def test_prompt_carries_vocabularies_page_text_and_an_untrusted_data_warning():
    system, user = llm.build_prompt(pages(), 24000)
    assert "general agent platform" in system and "market research" in system and "creators" in system
    assert "verbatim" in system
    assert "untrusted" in system and "instructions" in system
    assert "https://acme.test/" in user and "Acme sends each email campaign automatically." in user


def test_prompt_respects_the_character_budget_and_skips_javascript_shells():
    shell = parse_page("https://acme.test/app", html_page("<div id='root'></div><script src='/a.js'></script>"), Config())
    assert shell.needs_rendering
    _, user = llm.build_prompt([shell, *pages()], 300)
    assert "https://acme.test/app" not in user
    assert len(user) <= 300 + 200            # budget plus the fixed wrapper text


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Here you go:\n{"a": 1}\nDone.'])
def test_parse_output_accepts_fenced_or_wrapped_json(text):
    assert llm.parse_output(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "I cannot help with that.", "[1, 2]", '{"a": '])
def test_parse_output_rejects_everything_else(text):
    with pytest.raises(llm.LLMError) as err:
        llm.parse_output(text)
    assert err.value.error_type == "malformed_output"


# ------------------------------------------------------------------ validator
def test_validator_keeps_values_whose_quote_is_on_a_page():
    accepted, dropped = llm.validate(GOOD, pages())
    assert dropped == []
    assert [v for v, _ in accepted["target_user"]] == ["agencies", "ecommerce brands"]
    value, evidence = accepted["can_execute"][0]
    assert value is True and evidence.method == "llm" and evidence.url == "https://acme.test/"
    assert accepted["pricing"][0][0] == ("starting_price", "$29/month")
    assert accepted["hq_location"][0][0] == {"city": "Lisbon", "country": "Portugal"}


def test_quote_matching_ignores_case_and_whitespace_but_nothing_else():
    ok = {"tasks": [{"value": "send email campaigns", "quote": "ACME sends   each email\ncampaign automatically."}]}
    assert llm.validate(ok, pages())[1] == []
    reworded = {"tasks": [{"value": "send email campaigns", "quote": "Acme sends every email campaign automatically."}]}
    accepted, dropped = llm.validate(reworded, pages())
    assert accepted.get("tasks", []) == [] and dropped == [("tasks", "send email campaigns", "quote_not_found")]


@pytest.mark.parametrize("raw, reason", [
    ({"multi_agent": {"value": True, "quote": "A team of agents works together."}}, "quote_not_found"),      # hallucinated
    ({"categories": [{"value": "growth hacking", "quote": "Acme sends each email campaign automatically."}]}, "not_in_vocabulary"),
    ({"multi_agent": {"value": False, "quote": "Acme sends each email campaign automatically."}}, "multi_agent_cannot_be_false"),
    ({"can_execute": {"value": "yes", "quote": "Acme sends each email campaign automatically."}}, "not_a_boolean"),
    ({"integrations": [{"value": "HubSpot", "quote": "Acme integrates with Fernleaf CRM."}]}, "value_not_in_quote"),
    ({"pricing": {"starting_price": {"value": "$19/month", "quote": "Plans start at $29/month."}}}, "value_not_in_quote"),
    ({"hq_location": {"city": "Porto", "country": "Portugal", "quote": "We are headquartered in Lisbon, Portugal."}}, "value_not_in_quote"),
    ({"multi_agent": {"value": True, "quote": "Built for agencies and online stores."}}, "quote_does_not_mention_agents"),
    ({"tasks": [{"value": "write copy"}]}, "no_quote"),
    ({"tasks": [{"value": "write copy", "quote": "a"}]}, "no_quote"),
    ({"tasks": "write copy"}, "wrong_shape"),
])
def test_validator_drops(raw, reason):
    accepted, dropped = llm.validate(raw, pages())
    assert [d[2] for d in dropped] == [reason]
    assert not any(accepted.values())


# ------------------------------------------------------------------ merge
def test_merge_fills_unknowns_and_marks_method_llm():
    result = site_result()
    accepted, _ = llm.validate(GOOD, pages())
    added = llm.merge(result, accepted)
    fields = result["fields"]
    assert added == 9
    assert fields["can_execute"]["value"] is True
    assert fields["target_user"]["value"] == ["agencies", "ecommerce brands"]
    assert fields["pricing"]["value"] == {"free_tier": UNKNOWN, "starting_price": "$29/month"}
    assert fields["hq_location"]["value"] == {"city": "Lisbon", "country": "Portugal"}
    assert fields["multi_agent"]["value"] == UNKNOWN
    for name in FIELDS:
        assert all(e["method"] == "llm" for e in fields[name]["evidence"])


def test_merge_never_overrides_a_rule_based_value(events):
    rule = {"value": False, "evidence": [{"item": None, "url": "https://acme.test/", "quote": "Acme only drafts.", "method": "sentence"}]}
    lists = {"value": ["marketers"], "evidence": [{"item": "marketers", "url": "https://acme.test/", "quote": "For marketers.", "method": "sentence"}]}
    result = site_result(can_execute=rule, target_user=lists)
    accepted, _ = llm.validate({"can_execute": GOOD["can_execute"], "target_user": GOOD["target_user"]}, pages())
    llm.merge(result, accepted, site="acme")
    assert result["fields"]["can_execute"] == rule                                   # kept as it was
    assert result["fields"]["target_user"]["value"] == ["marketers", "agencies", "ecommerce brands"]
    assert [e["method"] for e in result["fields"]["target_user"]["evidence"]] == ["sentence", "llm", "llm"]
    assert any(e["error_type"] == "conflicts_with_rule_value" for e in events())


# ------------------------------------------------------------------ the pass for one site
def run_pass(answer, result=None, **kwargs):
    result = result or site_result()
    transport = FakeTransport(answer)
    outcome = llm.llm_pass(result, pages(), client(transport, **kwargs))
    return result, outcome, transport


def test_pass_success_records_counts(events):
    answer = dict(GOOD, multi_agent={"value": True, "quote": "A team of agents works together."})
    result, outcome, _ = run_pass(openai_answer(json.dumps(answer)))
    assert outcome == {"status": "ok", "added": 9, "dropped": 1, "error_type": None}
    assert result["llm"] == outcome
    assert result["fields"]["multi_agent"]["value"] == UNKNOWN             # the hallucinated quote was dropped
    log = events()
    dropped = [e for e in log if e["stage"] == "llm" and e["event"] == "skip"]
    assert dropped[0]["error_type"] == "quote_not_found" and dropped[0]["context"]["field"] == "multi_agent"
    done = [e for e in log if e["stage"] == "llm" and e["event"] == "success"]
    assert done and done[0]["context"]["added"] == 9 and done[0]["context"]["chars_sent"] > 100


@pytest.mark.parametrize("answer, error_type", [
    (FakeResponse(status=401, payload={}), "auth"),
    (FakeResponse(status=429, payload={}), "rate_limited"),
    (requests.exceptions.Timeout("slow"), "timeout"),
    (openai_answer("Sorry, here is no JSON."), "malformed_output"),
])
def test_pass_failure_keeps_the_rule_based_values(answer, error_type, events):
    before = site_result()
    snapshot = json.dumps(before["fields"], sort_keys=True)
    result, outcome, _ = run_pass(answer, result=before)
    assert outcome == {"status": "failed", "added": 0, "dropped": 0, "error_type": error_type}
    assert json.dumps(result["fields"], sort_keys=True) == snapshot
    failed = [e for e in events() if e["stage"] == "llm" and e["event"] == "fail"]
    assert failed and failed[-1]["error_type"] == error_type


def test_pass_is_skipped_when_there_is_nothing_readable():
    result = site_result()
    transport = FakeTransport(openai_answer("{}"))
    outcome = llm.llm_pass(result, [], client(transport))
    assert outcome["status"] == "skipped" and transport.calls == []


# ------------------------------------------------------------------ settings
def test_settings_come_from_config_and_environment(monkeypatch):
    monkeypatch.setenv("AGENT_SCOUT_LLM_API_KEY", KEY)
    monkeypatch.setenv("AGENT_SCOUT_LLM_MODEL", "env-model")
    config = LLMConfig(enabled=True, provider="openai-compatible", base_url="https://llm.test/v1", model="file-model")
    resolved = llm.resolve_settings(config)
    assert (resolved.provider, resolved.model, resolved.api_key) == ("openai-compatible", "file-model", KEY)
    assert KEY not in repr(resolved)
    config.model = None
    assert llm.resolve_settings(config).model == "env-model"


@pytest.mark.parametrize("env, config, fragment", [
    ({}, dict(provider="openai-compatible", base_url="https://x/v1", model="m"), "AGENT_SCOUT_LLM_API_KEY"),
    ({"AGENT_SCOUT_LLM_API_KEY": KEY}, dict(model="m"), "provider"),
    ({"AGENT_SCOUT_LLM_API_KEY": KEY}, dict(provider="anthropic"), "model"),
    ({"AGENT_SCOUT_LLM_API_KEY": KEY}, dict(provider="openai-compatible", model="m"), "base URL"),
    ({"AGENT_SCOUT_LLM_API_KEY": KEY}, dict(provider="mystery", model="m"), "provider"),
])
def test_incomplete_settings_are_one_line_errors_without_the_key(monkeypatch, env, config, fragment):
    for name in ("AGENT_SCOUT_LLM_API_KEY", "AGENT_SCOUT_LLM_PROVIDER", "AGENT_SCOUT_LLM_BASE_URL", "AGENT_SCOUT_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(llm.LLMError) as err:
        llm.resolve_settings(LLMConfig(enabled=True, **config))
    assert fragment in str(err.value) and KEY not in str(err.value) and "\n" not in str(err.value)


# ------------------------------------------------------------------ end to end through the CLI
@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("AGENT_SCOUT_LLM_API_KEY", KEY)
    monkeypatch.setenv("AGENT_SCOUT_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AGENT_SCOUT_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("AGENT_SCOUT_LLM_MODEL", "test-model")


def run_cli(tmp_path, fixture_sites, slugs, extra=()):
    from agent_scout.cli import main
    sites = tmp_path / "sites.yaml"
    sites.write_text("".join(f"- slug: {s}\n  name: \"{fixture_sites[s].name}\"\n  url: {fixture_sites[s].url}\n" for s in slugs),
                     encoding="utf-8")
    code = main(["run", str(sites), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs"),
                 "--delay", "0", *extra])
    return code


def everything_written(tmp_path):
    return "".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file())


def test_cli_llm_run_merges_verified_values_and_never_writes_the_key(tmp_path, fixture_sites, llm_env, monkeypatch, capsys):
    answer = {"categories": [{"value": "analytics & reporting", "quote": "Weekly performance reports show revenue per campaign."}],
              "tasks": [{"value": "market research", "quote": "This sentence is not on the site."}],
              "can_execute": {"value": True, "quote": "The agent adjusts ad budgets and bids on its own when the cost per order rises."}}
    transport = FakeTransport(openai_answer(json.dumps(answer)))
    monkeypatch.setattr(llm, "default_transport", lambda: transport)
    code = run_cli(tmp_path, fixture_sites, ["northwind", "palisade"], ["--llm"])
    captured = capsys.readouterr()
    assert code == 0
    results = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    northwind, palisade = results["sites"]
    assert northwind["llm"] == {"status": "ok", "added": 1, "dropped": 1, "error_type": None}
    assert northwind["fields"]["categories"]["value"] == ["email marketing", "advertising", "analytics & reporting"]
    assert "market research" not in northwind["fields"]["tasks"]["value"]
    assert northwind["fields"]["categories"]["evidence"][-1]["method"] == "llm"
    assert northwind["fields"]["can_execute"]["evidence"][0]["method"] == "meta"      # already known by rule: unchanged
    assert palisade["llm"]["status"] == "skipped" and len(transport.calls) == 1     # a blocked site sends nothing
    assert results["settings"]["llm"] == {"enabled": True, "provider": "openai-compatible", "model": "test-model"}
    assert "LLM, quote verified" in (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert KEY not in everything_written(tmp_path) and KEY not in captured.out and KEY not in captured.err
    sent = transport.calls[0]["json"]["messages"][1]["content"]
    assert "Campaign Pilot" in sent and "multi-agent team" not in sent        # robots-disallowed page text is never sent


def test_cli_llm_auth_failure_is_exit_1_keeps_rule_values_and_stops_calling(tmp_path, fixture_sites, llm_env, monkeypatch, capsys):
    transport = FakeTransport(FakeResponse(status=401, payload={"error": f"invalid {KEY}"}))
    monkeypatch.setattr(llm, "default_transport", lambda: transport)
    code = run_cli(tmp_path, fixture_sites, ["northwind", "quillmate"], ["--llm", "--quiet"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.count("\n") == 1 and "LLM pass failed" in captured.err and "auth" in captured.err
    results = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert [site["llm"]["status"] for site in results["sites"]] == ["failed", "skipped"]
    assert results["sites"][0]["fields"]["can_execute"]["value"] is True          # rule-based values are intact
    assert len(transport.calls) == 1
    assert KEY not in everything_written(tmp_path) and KEY not in captured.err


def test_cli_llm_without_key_is_exit_1_before_any_request(tmp_path, fixture_sites, monkeypatch, capsys):
    for name in ("AGENT_SCOUT_LLM_API_KEY", "AGENT_SCOUT_LLM_PROVIDER", "AGENT_SCOUT_LLM_BASE_URL", "AGENT_SCOUT_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    site = fixture_sites["northwind"]
    del site.requests[:]
    code = run_cli(tmp_path, fixture_sites, ["northwind"], ["--llm", "--llm-provider", "anthropic", "--llm-model", "m"])
    assert code == 1
    assert "AGENT_SCOUT_LLM_API_KEY" in capsys.readouterr().err
    assert site.requests == []


def test_llm_is_off_by_default(tmp_path, fixture_sites, monkeypatch):
    def boom():
        raise AssertionError("the LLM transport must not be created without --llm")
    monkeypatch.setattr(llm, "default_transport", boom)
    assert run_cli(tmp_path, fixture_sites, ["glimmer"], ["--quiet"]) == 0
    results = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert results["settings"]["llm"]["enabled"] is False and results["sites"][0]["llm"] is None
