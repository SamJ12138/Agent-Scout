"""scripts/demo.py, scripts/score.py and the hook installer."""

import json
import subprocess
import sys
from pathlib import Path

import demo
import install_hooks
import score

ROOT = Path(__file__).resolve().parents[1]


def test_demo_runs_offline_and_says_where_the_reports_are(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(demo, "DEMO_PORT", 0)          # any free port, so parallel runs cannot collide
    code = demo.main(["--out", str(tmp_path / "demo"), "--delay", "0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "fictional sample sites" in out and "not real products" in out
    report = tmp_path / "demo" / "reports" / "report.html"
    assert report.is_file() and str(report) in out
    results = json.loads((tmp_path / "demo" / "reports" / "results.json").read_text(encoding="utf-8"))
    assert [site["status"] for site in results["sites"]] == ["ok", "ok", "ok", "partial", "blocked", "robots_disallowed"]
    assert all("(fictional)" in site["name"] for site in results["sites"])


def test_score_script_exit_codes(tmp_path, capsys):
    truth = ROOT / "tests" / "fixtures" / "ground-truth"
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"sites": []}), encoding="utf-8")
    assert score.main([str(results), str(truth)]) == 0
    assert "no result for ground-truth site: northwind" in capsys.readouterr().out
    assert score.main([str(results), str(truth), "--require-all-match"]) == 1
    assert score.main([str(tmp_path / "missing.json"), str(truth)]) == 1
    assert score.main([str(results), str(tmp_path / "nowhere")]) == 1


def test_install_hooks_points_git_at_the_hook_directory(tmp_path, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert install_hooks.install(tmp_path) == 1                      # the hook file is not there yet
    (tmp_path / "scripts" / "hooks").mkdir(parents=True)
    (tmp_path / "scripts" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert install_hooks.install(tmp_path) == 0
    configured = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path, capture_output=True, text=True)
    assert configured.stdout.strip() == "scripts/hooks"


def test_pre_commit_hook_runs_the_suite():
    hook = (ROOT / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert hook.startswith("#!/bin/sh") and "-m pytest" in hook
    assert sys.executable            # the hook picks the project's interpreter when a .venv exists
