"""Command line: exit codes 0 (ok), 1 (error, one-line message), 2 (usage)."""

import pytest

from agent_scout import __version__, obs
from agent_scout.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def test_unknown_option_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main(["report-log", "--nope"])
    assert exit_info.value.code == 2


def test_report_log_ok(tmp_path, capsys):
    log = obs.EventLog(tmp_path / "run_a.jsonl", run_id="a")
    log.emit("fetch", "fail", site="s", duration_ms=5, error_type="http_403")
    log.close()
    assert main(["report-log", str(tmp_path / "run_a.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "http_403" in out and "p95" in out


def test_report_log_missing_file_is_exit_1_with_one_line(tmp_path, capsys):
    assert main(["report-log", str(tmp_path / "missing.jsonl")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("agent-scout: error: ")
    assert captured.err.count("\n") == 1


def test_run_missing_sites_file_is_exit_1(tmp_path, capsys):
    code = main(["run", str(tmp_path / "nope.yaml"), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("agent-scout: error: cannot read sites file")
    assert captured.err.count("\n") == 1 and "Traceback" not in captured.err
    assert not (tmp_path / "out").exists()


def test_run_bad_config_is_exit_1(tmp_path, capsys):
    sites = tmp_path / "sites.txt"
    sites.write_text("http://127.0.0.1:9/\n", encoding="utf-8")
    config = tmp_path / "c.yaml"
    config.write_text("page_budget: 0\n", encoding="utf-8")
    code = main(["run", str(sites), "--config", str(config), "-o", str(tmp_path / "out"),
                 "--log-dir", str(tmp_path / "logs")])
    assert code == 1
    assert "page_budget" in capsys.readouterr().err


def test_run_without_sites_argument_is_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main(["run"])
    assert exit_info.value.code == 2


def test_run_bad_option_value_is_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main(["run", "sites.yaml", "--delay", "fast"])
    assert exit_info.value.code == 2


def test_run_on_an_unreachable_site_is_still_exit_0(tmp_path, capsys):
    sites = tmp_path / "sites.txt"
    sites.write_text("http://127.0.0.1:9/\n", encoding="utf-8")
    code = main(["run", str(sites), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs"),
                 "--delay", "0", "--timeout", "2"])
    out = capsys.readouterr().out
    assert code == 0
    assert "unreachable" in out and "every field is unknown" in out
    assert (tmp_path / "out" / "results.json").is_file()


def test_run_output_directory_that_is_a_file_is_exit_1(tmp_path, capsys):
    sites = tmp_path / "sites.txt"
    sites.write_text("http://127.0.0.1:9/\n", encoding="utf-8")
    blocker = tmp_path / "out"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    code = main(["run", str(sites), "-o", str(blocker), "--log-dir", str(tmp_path / "logs"),
                 "--delay", "0", "--timeout", "2", "--quiet"])
    assert code == 1
    assert "cannot write reports" in capsys.readouterr().err


def test_python_dash_m_entry_point():
    import subprocess
    import sys
    done = subprocess.run([sys.executable, "-m", "agent_scout", "--version"], capture_output=True, text=True)
    assert done.returncode == 0 and __version__ in done.stdout


def test_console_that_cannot_encode_a_site_name_does_not_crash_the_run(tmp_path, monkeypatch):
    import io
    import sys
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii"))
    sites = tmp_path / "sites.yaml"
    sites.write_text('- name: "Café → Agent 東京 (fictional)"\n  url: http://127.0.0.1:9/\n', encoding="utf-8")
    code = main(["run", str(sites), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs"),
                 "--delay", "0", "--timeout", "2"])
    sys.stdout.flush()
    assert code == 0
    assert b"Caf\\xe9" in raw.getvalue()
    assert "Café → Agent 東京" in (tmp_path / "out" / "report.html").read_text(encoding="utf-8")


def test_unexpected_exception_is_one_line_exit_1_and_is_logged(tmp_path, capsys, monkeypatch):
    import json
    from agent_scout import pipeline
    sites = tmp_path / "sites.txt"
    sites.write_text("http://127.0.0.1:9/\n", encoding="utf-8")

    def explode(*args, **kwargs):
        raise RuntimeError("something nobody planned for")
    monkeypatch.setattr(pipeline, "crawl_site", explode)
    monkeypatch.delenv("AGENT_SCOUT_TRACEBACK", raising=False)
    code = main(["run", str(sites), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs"), "--quiet"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.count("\n") == 1 and "RuntimeError" in captured.err and "Traceback" not in captured.err
    log = next((tmp_path / "logs").glob("run_*.jsonl"))
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    crash = [e for e in events if e["error_type"] == "RuntimeError" and "traceback" in e["context"]]
    assert crash and "something nobody planned for" in crash[-1]["context"]["traceback"]
    monkeypatch.setenv("AGENT_SCOUT_TRACEBACK", "1")
    assert main(["run", str(sites), "-o", str(tmp_path / "out"), "--log-dir", str(tmp_path / "logs"), "--quiet"]) == 1
    assert "Traceback" in capsys.readouterr().err
