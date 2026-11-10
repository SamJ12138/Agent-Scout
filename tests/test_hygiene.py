"""Nothing personal and no tool attribution in any tracked file or commit message."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".ico", ".woff", ".woff2", ".pdf"}

# Built from pieces so that this file does not match itself.
PERSONAL = [
    ("a local user name", re.compile("isa" + "mb", re.IGNORECASE)),
    ("a Windows home path", re.compile(r"C:\\+" + "Users", re.IGNORECASE)),
    ("a macOS or Linux home path", re.compile(r"/(?:Users|home)/[a-z][\w.-]*/", re.IGNORECASE)),
    ("a personal mail address", re.compile(r"[\w.+-]+@" + "gmail" + r"\.com", re.IGNORECASE)),
    ("a college mail address", re.compile(r"[\w.+-]*@?" + "gettys" + r"burg\.edu", re.IGNORECASE)),
]
ATTRIBUTION = [
    ("a co-author trailer", re.compile("Co-Authored" + "-By", re.IGNORECASE)),
    ("a session trailer", re.compile("Claude" + "-Session", re.IGNORECASE)),
    ("a generated-with line", re.compile("Generated " + r"with \[?Claude", re.IGNORECASE)),
    ("a session link", re.compile(r"claude\.ai/" + "code", re.IGNORECASE)),
]


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
        if path.suffix.lower() in BINARY:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in PERSONAL + ATTRIBUTION:
            match = pattern.search(text)
            if match:
                problems.append(f"{path.relative_to(ROOT)}: {label} ({match.group(0)!r})")
    assert not problems, "\n".join(problems)


def test_commit_messages_hold_no_personal_data():
    log = git("log", "--format=%an <%ae>%n%B")
    if log is None or not log.strip():
        pytest.skip("no git history available")
    for label, pattern in PERSONAL:
        match = pattern.search(log)
        assert not match, f"commit history contains {label}: {match.group(0)!r}"


def test_the_word_gmail_alone_is_allowed():
    """Real ground truth lists Gmail as an integration; only addresses are personal data."""
    assert not any(pattern.search("Integrates with Gmail and Slack.") for _, pattern in PERSONAL)
    assert any(pattern.search("write to someone@" + "gmail.com") for _, pattern in PERSONAL)


def test_fixture_sites_say_they_are_fictional_on_every_page():
    sites = ROOT / "tests" / "fixtures" / "sites"
    pages = list(sites.rglob("*.html"))
    assert len(pages) >= 30
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "ictional" in text, f"{page.relative_to(ROOT)} does not say it is fictional"
    import json
    for config in sites.glob("*/_site.json"):
        assert json.loads(config.read_text(encoding="utf-8"))["name"].endswith("(fictional)")
