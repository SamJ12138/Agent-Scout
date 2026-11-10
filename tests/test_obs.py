"""Observability: JSONL event log, spans, secret redaction, report-log."""

import ast
import json
from pathlib import Path

import pytest

from agent_scout import obs

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_scout"
EVENT_KEYS = {"ts", "run_id", "site", "stage", "event", "duration_ms", "error_type", "context"}


def read_events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_every_event_is_one_json_line_with_all_keys(tmp_path):
    log = obs.EventLog(tmp_path / "run_x.jsonl", run_id="x")
    log.emit("fetch", "success", site="s1", duration_ms=12, url="http://h/", status=200)
    log.emit("fetch", "fail", site="s1", error_type="timeout")
    log.close()
    events = read_events(tmp_path / "run_x.jsonl")
    assert len(events) == 2
    for event in events:
        assert set(event) == EVENT_KEYS
        assert event["run_id"] == "x"
    assert events[0]["context"] == {"url": "http://h/", "status": 200}
    assert events[1]["error_type"] == "timeout"
    assert events[1]["duration_ms"] is None


def test_unknown_event_name_is_rejected(tmp_path):
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    with pytest.raises(ValueError):
        log.emit("fetch", "finished")
    log.close()


def test_span_emits_start_then_success_with_duration(tmp_path):
    ticks = iter([10.0, 10.25])
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x", perf=lambda: next(ticks))
    with log.span("extract", site="s1", field="pricing") as span:
        span.context["method"] = "table"
    log.close()
    start, done = read_events(tmp_path / "a.jsonl")
    assert (start["event"], done["event"]) == ("start", "success")
    assert done["duration_ms"] == 250
    assert done["context"] == {"field": "pricing", "method": "table"}


def test_span_marks_fail_and_skip(tmp_path):
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    with log.span("fetch", site="s1") as span:
        span.fail("http_503")
    with log.span("fetch", site="s1") as span:
        span.skip("robots_disallowed")
    log.close()
    events = read_events(tmp_path / "a.jsonl")
    assert [(e["event"], e["error_type"]) for e in events if e["event"] != "start"] == [
        ("fail", "http_503"),
        ("skip", "robots_disallowed"),
    ]


def test_span_logs_exception_type_and_reraises(tmp_path):
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    with pytest.raises(KeyError):
        with log.span("parse", site="s1"):
            raise KeyError("boom")
    log.close()
    last = read_events(tmp_path / "a.jsonl")[-1]
    assert (last["event"], last["error_type"]) == ("fail", "KeyError")


def test_registered_secret_never_reaches_the_log(tmp_path):
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    log.register_secret("sk-TESTSECRET123")
    log.emit("llm", "fail", error_type="auth", detail="bad key sk-TESTSECRET123 rejected",
             nested={"header": "Bearer sk-TESTSECRET123"})
    log.close()
    text = (tmp_path / "a.jsonl").read_text(encoding="utf-8")
    assert "sk-TESTSECRET123" not in text
    assert "[redacted]" in text


def test_module_level_emit_uses_current_log_and_is_safe_without_one(tmp_path):
    obs.set_current(None)
    obs.emit("fetch", "success")  # must not raise
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    obs.set_current(log)
    try:
        obs.emit("fetch", "skip", site="s", error_type="robots_disallowed")
    finally:
        obs.set_current(None)
        log.close()
    assert read_events(tmp_path / "a.jsonl")[0]["event"] == "skip"


def test_percentile_nearest_rank():
    assert obs.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert obs.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert obs.percentile([7], 95) == 7


def test_report_log_counts_errors_and_durations(tmp_path):
    log = obs.EventLog(tmp_path / "a.jsonl", run_id="x")
    for ms in (10, 20, 30, 40):
        log.emit("fetch", "success", site="a", duration_ms=ms)
    log.emit("fetch", "fail", site="b", duration_ms=50, error_type="http_403")
    log.emit("fetch", "fail", site="c", duration_ms=60, error_type="http_403")
    log.emit("robots", "skip", site="d", error_type="robots_5xx")
    log.close()
    text = obs.report_log(tmp_path / "a.jsonl")
    rows = {tuple(line.split()) for line in text.splitlines()}
    assert ("fetch", "http_403", "fail", "2") in rows
    assert ("robots", "robots_5xx", "skip", "1") in rows
    # per-stage p50 / p95 over events that carry a duration
    assert ("fetch", "6", "30", "60") in rows


def test_report_log_rejects_a_file_that_is_not_a_run_log(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    with pytest.raises(obs.LogFormatError):
        obs.report_log(bad)


def _handler_logs(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"emit", "fail", "skip"}:
                return True
    return False


def test_every_except_block_logs():
    """An except block that swallows or converts an error must leave a log event."""
    missing = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and not _handler_logs(node):
                missing.append(f"{path.name}:{node.lineno}")
    assert not missing, f"except blocks without a log call: {missing}"
