"""Nothing personal and no tool attribution in any tracked file.

Commit messages are checked when they are written, by scripts/hooks/commit-msg
(installed with scripts/install_hooks.py), not by this suite: a test over the
history cannot be made green again without rewriting that history.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import hygiene

ROOT = Path(__file__).resolve().parents[1]
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".ico", ".woff", ".woff2", ".pdf"}


def git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def tracked_files() -> list[Path]:
    listing = git("ls-files")
    if listing is None:                      # not a git checkout (e.g. a source archive): walk the tree
        skip = {".git", ".venv", "__pycache__", ".pytest_cache", "out", "logs", "demo-output"}
        return [p for p in ROOT.rglob("*") if p.is_file() and not skip.intersection(p.relative_to(ROOT).parts)
                and ".egg-info" not in str(p)]
    return [ROOT / line for line in listing.splitlines() if line and (ROOT / line).is_file()]


def test_tracked_files_hold_no_personal_data_and_no_attribution():
    problems = []
    files = tracked_files()
    assert len(files) > 50
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in BINARY or relative in hygiene.WRITTEN_BY_THE_CORPUS_WORKFLOW:
            continue
        for label, found in hygiene.findings(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"{relative}: {label} ({found!r})")
    assert not problems, "\n".join(problems)


# Each example is assembled from pieces so that this file stays clean itself.
USER = "isa" + "mb"
@pytest.mark.parametrize("text, flagged", [
    ("C:\\" + "Users\\" + USER + "\\Documents", True),
    ("saved by " + USER + " yesterday", True),
    ("Isa" + "mbard Kingdom Brunel built bridges", False),            # the name only as a whole word
    ("write to someone@" + "gmail.com", True),
    ("Integrates with Gmail and Slack.", False),                       # the word alone is a product name
    ("ask jane@" + "gettys" + "burg.edu", True),
    ("stored under /home/" + "someone/notes.txt", True),
    ("open /Users/" + "someone/Desktop/a.txt", True),
    ('"url": "https://site.example/home/pricing/"', False),            # a URL path
    ("the pattern matched URL paths such as /home/pricing/ and no more", False),
    ("Co-Authored" + "-By: Somebody", True),
    ("Generated " + "with [Claude" + " Code]", True),
    ("Claude" + "-Session: https://example.test/x", True),
    ("Klaviyo lists Claude as an integration.", False),                # a product name on a real site
])
def test_patterns(text, flagged):
    assert bool(hygiene.findings(text)) is flagged, hygiene.findings(text)


def test_workflow_outputs_are_not_scanned():
    """Text quoted from real websites by the corpus workflow must not turn CI red."""
    assert hygiene.WRITTEN_BY_THE_CORPUS_WORKFLOW == {
        "docs/real-corpus/results/latest.json", "docs/real-corpus/report.html", "docs/real-corpus/scores.md"}
    workflow = (ROOT / ".github" / "workflows" / "corpus.yml").read_text(encoding="utf-8")
    for path in hygiene.WRITTEN_BY_THE_CORPUS_WORKFLOW:
        assert path in workflow


def test_commit_message_check(tmp_path, capsys):
    good = tmp_path / "good.txt"
    good.write_text("fix: a thing\n\nBody text about /home/pricing/ style URL paths.\n", encoding="utf-8")
    assert hygiene.main(["--commit-message", str(good)]) == 0
    bad = tmp_path / "bad.txt"
    bad.write_text("fix: a thing\n\nCo-Authored" + "-By: Somebody <a@b.test>\n", encoding="utf-8")
    assert hygiene.main(["--commit-message", str(bad)]) == 1
    assert "co-author" in capsys.readouterr().err
    commented = tmp_path / "commented.txt"
    commented.write_text("fix: a thing\n# Co-Authored" + "-By: in a comment line git will drop\n", encoding="utf-8")
    assert hygiene.main(["--commit-message", str(commented)]) == 0


def test_commit_msg_hook_calls_the_check():
    hook = (ROOT / "scripts" / "hooks" / "commit-msg").read_text(encoding="utf-8")
    assert hook.startswith("#!/bin/sh") and "scripts/hygiene.py" in hook and "--commit-message" in hook
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "hygiene.py"), "--help"], capture_output=True, text=True)
    assert done.returncode == 0


def test_fixture_sites_say_they_are_fictional_on_every_page():
    sites = ROOT / "tests" / "fixtures" / "sites"
    pages = list(sites.rglob("*.html"))
    assert len(pages) >= 30
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "ictional" in text, f"{page.relative_to(ROOT)} does not say it is fictional"
    for config in sites.glob("*/_site.json"):
        assert json.loads(config.read_text(encoding="utf-8"))["name"].endswith("(fictional)")
