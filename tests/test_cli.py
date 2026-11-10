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
