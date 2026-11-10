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
    assert "[skip ci]" in text and "scripts/run_corpus.py" in text
    assert 'git config user.name "Tianyi Jia"' in text and "github-actions[bot]" not in text
    # the files the workflow commits must not be among the paths that trigger it
    for written in ("docs/real-corpus/results/latest.json", "docs/real-corpus/scores.md", "docs/real-corpus/report.html"):
        assert written in text and not any(written.startswith(path.rstrip("*")) for path in triggers["push"]["paths"])
    ci = yaml.safe_load((root / "ci.yml").read_text(encoding="utf-8"))
    matrix = ci["jobs"]["test"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-24.04", "windows-2025"] and matrix["python-version"] == ["3.10", "3.13"]
    for workflow in (corpus, ci):
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    assert step["uses"] in ("actions/checkout@v7", "actions/setup-python@v7",
                                            "actions/upload-artifact@v7"), step["uses"]


# ------------------------------------------------------------------ README "Real-site results": no hand-typed numbers
README = run_corpus.ROOT / "README.md"


def test_scores_file_is_parsed():
    parsed = run_corpus.parse_scores((run_corpus.CORPUS / "run-1" / "scores.md").read_text(encoding="utf-8"))
    assert parsed["run_id"] == "20261110T141046Z-418b" and parsed["finished"] == "2026-11-10T14:12:34Z"
    assert (parsed["sites_read"], parsed["sites"]) == (10, 10)
    assert parsed["totals"] == {"match": 30, "partial": 43, "mismatch": 4, "missing": 13} and parsed["site_fields"] == 90
    assert parsed["fields"]["one_liner"] == {"match": 6, "partial": 4, "mismatch": 0, "missing": 0}
    assert set(parsed["fields"]) == set(scoring.FIELDS)
    assert sum(sum(row.values()) for row in parsed["fields"].values()) == 90


def test_readme_results_block_is_generated_from_the_latest_scores():
    text = README.read_text(encoding="utf-8")
    start, end = text.index(run_corpus.README_START), text.index(run_corpus.README_END)
    block = text[start:end + len(run_corpus.README_END)]
    scores = run_corpus.parse_scores((run_corpus.CORPUS / "scores.md").read_text(encoding="utf-8"))
    assert block == run_corpus.readme_block(scores, run_corpus.first_run_id()), \
        "run scripts/run_corpus.py, or update the README block"
    assert text.index("## Real-site results") < text.index("## Quickstart")       # near the top


def test_readme_keeps_the_first_run_as_the_before_figure():
    first = run_corpus.parse_scores((run_corpus.CORPUS / "run-1" / "scores.md").read_text(encoding="utf-8"))
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert run_corpus.totals_sentence(first) in text
    assert "docs/real-corpus/run-1/scores.md" in text
    assert "not a clean held-out score" in text
    assert "docs/real-corpus/report.html" in text and "docs/real-corpus/scores.md" in text


def test_run_corpus_rewrites_only_the_marked_block_of_a_readme(tmp_path, fixture_sites):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\nbefore\n\n{run_corpus.README_START}\nold numbers\n{run_corpus.README_END}\n\nafter\n",
                      encoding="utf-8")
    sites = tmp_path / "sites.yaml"
    sites.write_text(fixture_sites.sites_yaml(), encoding="utf-8")
    code = run_corpus.main(["--sites", str(sites), "--ground-truth", str(GROUND_TRUTH_DIR), "--out", str(tmp_path / "c"),
                            "--delay", "0", "--readme", str(readme)])
    assert code == 0
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("# Title\n\nbefore\n\n") and text.endswith("\n\nafter\n")
    assert "old numbers" not in text and "54 match, 0 partial, 0 mismatch, 0 missing" in text and "Sites read: 4 of 6" in text


def test_run_corpus_leaves_the_project_readme_alone_when_writing_elsewhere(tmp_path, fixture_sites):
    before = README.read_text(encoding="utf-8")
    sites = tmp_path / "sites.yaml"
    sites.write_text(fixture_sites.sites_yaml(), encoding="utf-8")
    assert run_corpus.main(["--sites", str(sites), "--ground-truth", str(GROUND_TRUTH_DIR), "--out", str(tmp_path / "c"),
                            "--delay", "0"]) == 0
    assert README.read_text(encoding="utf-8") == before


def test_corpus_workflow_commits_the_readme_block_too():
    text = (run_corpus.ROOT / ".github" / "workflows" / "corpus.yml").read_text(encoding="utf-8")
    add_line = next(line for line in text.splitlines() if "git add" in line)
    assert "README.md" in add_line
    corpus = yaml.safe_load(text)
    triggers = corpus[True] if True in corpus else corpus["on"]
    assert "README.md" not in triggers["push"]["paths"]            # so the commit cannot start the workflow again


def test_the_block_says_whether_rules_changed_since_the_run():
    first = run_corpus.parse_scores((run_corpus.CORPUS / "run-1" / "scores.md").read_text(encoding="utf-8"))
    assert "first run on real sites" in run_corpus.readme_block(first, first["run_id"])
    later = dict(first, run_id="20270101T000000Z-0000")
    assert "not a held-out score" in run_corpus.readme_block(later, first["run_id"])


# ------------------------------------------------------------------ run 2 and what it got wrong stay on record
def _outside_the_generated_block(text):
    start, end = text.index(run_corpus.README_START), text.index(run_corpus.README_END)
    return " ".join((text[:start] + text[end + len(run_corpus.README_END):]).split())


def test_the_second_run_is_kept_as_history():
    second = run_corpus.parse_scores((run_corpus.CORPUS / "run-2" / "scores.md").read_text(encoding="utf-8"))
    assert second["run_id"] == "20261110T143957Z-27a7"
    assert second["totals"] == {"match": 37, "partial": 40, "mismatch": 2, "missing": 11} and second["site_fields"] == 90
    assert "- adcreative-ai / hq_location: mismatch" in (run_corpus.CORPUS / "run-2" / "scores.md").read_text(
        encoding="utf-8")


def test_readme_shows_run_1_then_run_2_then_the_latest():
    first = run_corpus.parse_scores((run_corpus.CORPUS / "run-1" / "scores.md").read_text(encoding="utf-8"))
    second = run_corpus.parse_scores((run_corpus.CORPUS / "run-2" / "scores.md").read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")
    permanent = _outside_the_generated_block(readme)          # typed text: it must agree with the kept files
    assert run_corpus.totals_sentence(first) in permanent and run_corpus.totals_sentence(second) in permanent
    assert permanent.index(run_corpus.totals_sentence(first)) < permanent.index(run_corpus.totals_sentence(second))
    assert "docs/real-corpus/run-1/scores.md" in permanent and "docs/real-corpus/run-2/scores.md" in permanent
    assert "docs/real-corpus/scores.md" in permanent           # the latest


def test_readme_says_what_run_2_got_wrong():
    permanent = _outside_the_generated_block(README.read_text(encoding="utf-8"))
    assert "wrong headquarters" in permanent and "hosting provider" in permanent and "legal notice" in permanent
    assert "a host's address in a legal notice is not the headquarters" in permanent    # the commit that fixed it


def test_known_disagreements_with_the_reference_are_listed():
    text = " ".join((run_corpus.CORPUS / "README.md").read_text(encoding="utf-8").split())
    assert "## Known disagreements with the reference" in text
    assert "relevance-ai / pricing" in text and '"Get Started for free."' in text
    assert "https://relevanceai.com/integrations" in text
    assert "not edited after the fact" in text
    assert "run-2/scores.md" in text
