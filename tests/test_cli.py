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
