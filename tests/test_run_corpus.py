"""scripts/run_corpus.py, exercised on the fictional fixture sites."""

import json

import yaml

import run_corpus
from agent_scout.inputs import load_sites
from agent_scout import scoring
from fixture_server import GROUND_TRUTH_DIR


def test_run_corpus_writes_three_outputs_and_blocked_sites_do_not_fail_it(tmp_path, fixture_sites, capsys):
    sites = tmp_path / "sites.yaml"
    sites.write_text(fixture_sites.sites_yaml(), encoding="utf-8")
    out = tmp_path / "corpus"
    code = run_corpus.main(["--sites", str(sites), "--ground-truth", str(GROUND_TRUTH_DIR), "--out", str(out),
                            "--keep-run-dir", str(tmp_path / "run"), "--delay", "0"])
    assert code == 0                                           # palisade is blocked, tessera ruled out: still 0
    results = json.loads((out / "results" / "latest.json").read_text(encoding="utf-8"))
    assert len(results["sites"]) == 6
    assert (out / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    scores = (out / "scores.md").read_text(encoding="utf-8")
    assert "| palisade | blocked |" in scores and "| tessera | ruled out by robots.txt |" in scores
    assert "Sites read: 4 of 6" in scores
    assert "54 match, 0 partial, 0 mismatch, 0 missing, of 54" in scores
    for slug in ("northwind", "quillmate", "orbitfleet", "glimmer"):
        assert f"| {slug} |" in scores
    assert list((tmp_path / "run" / "logs").glob("run_*.jsonl"))
    assert "54 match" in capsys.readouterr().out


def test_run_corpus_fails_when_the_tool_fails(tmp_path, capsys):
    code = run_corpus.main(["--sites", str(tmp_path / "missing.yaml"), "--ground-truth", str(tmp_path),
                            "--out", str(tmp_path / "corpus")])
    assert code == 1
    assert not (tmp_path / "corpus").exists()
    assert "nothing was written" in capsys.readouterr().err


def test_real_corpus_files_are_loadable_and_paired():
    """The committed real-site list and ground truth agree with each other."""
    sites = load_sites(run_corpus.CORPUS / "sites.yaml")
    truth = scoring.load_ground_truth(run_corpus.CORPUS / "ground-truth")
    assert sites and {site.slug for site in sites} == set(truth)
    for slug, doc in truth.items():
        assert set(doc["fields"]) == set(scoring.FIELDS), slug
        # every reference value can be compared with itself and comes out as a match
        for name, entry in doc["fields"].items():
            assert scoring.compare_entry(name, entry, entry["value"]).outcome == "match", (slug, name)


def test_real_corpus_vocabulary_values_are_schema_values():
    from agent_scout import vocab
    truth = scoring.load_ground_truth(run_corpus.CORPUS / "ground-truth")
    tables = {"categories": vocab.CATEGORIES, "target_user": vocab.TARGET_USERS, "tasks": vocab.TASKS}
    for slug, doc in truth.items():
        for name, table in tables.items():
            value = doc["fields"][name]["value"]
            assert value == "unknown" or set(value) <= set(table), (slug, name, value)


def test_workflows_are_valid_yaml_with_the_agreed_shape():
    root = run_corpus.ROOT / ".github" / "workflows"
    corpus = yaml.safe_load((root / "corpus.yml").read_text(encoding="utf-8"))
    triggers = corpus[True] if True in corpus else corpus["on"]          # YAML reads the key "on" as a boolean
    assert "workflow_dispatch" in triggers
    assert triggers["push"]["branches"] == ["main"]
    assert set(triggers["push"]["paths"]) == {"src/**", "docs/real-corpus/sites.yaml", "docs/real-corpus/ground-truth/**"}
    assert corpus["permissions"] == {"contents": "write"}
    text = (root / "corpus.yml").read_text(encoding="utf-8")
    assert "[skip ci]" in text and "github-actions[bot]" in text and "scripts/run_corpus.py" in text
    ci = yaml.safe_load((root / "ci.yml").read_text(encoding="utf-8"))
    matrix = ci["jobs"]["test"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-24.04", "windows-2025"] and matrix["python-version"] == ["3.12"]
    for workflow in (corpus, ci):
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    assert step["uses"] in ("actions/checkout@v7", "actions/setup-python@v7",
                                            "actions/upload-artifact@v7"), step["uses"]
