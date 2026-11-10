"""Patterns that must not appear in tracked files or commit messages:
personal data of the owner and tool-attribution lines.

    python scripts/hygiene.py --commit-message FILE    # used by scripts/hooks/commit-msg

tests/test_hygiene.py applies the same patterns to every tracked text file.
The patterns are assembled from pieces so that this file does not match itself.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern]] = [
    # the owner's local account name, as a whole word
    ("a local user name", re.compile(r"\b" + "isa" + r"mb\b", re.IGNORECASE)),
    ("a Windows home path", re.compile(r"C:\\+" + r"Users\\", re.IGNORECASE)),
    # /home/<user>/<something> or /Users/<user>/<something> as a filesystem path: not preceded by
    # a host or another path segment, and with something after the user directory. The path
    # part of a URL ("https://site.example/home/pricing/") and a bare "/home/pricing/" in prose
    # do not match.
    ("a macOS or Linux home path", re.compile(r"(?<![\w.:/-])/(?:Users|home)/[a-z][\w.-]*/[\w.-]+", re.IGNORECASE)),
    ("a personal mail address", re.compile(r"[\w.+-]+@" + "gmail" + r"\.com", re.IGNORECASE)),
    ("a college mail address", re.compile(r"[\w.+-]*@" + "gettys" + r"burg\.edu", re.IGNORECASE)),
    ("a co-author trailer", re.compile("Co-Authored" + "-By", re.IGNORECASE)),
    ("a session trailer", re.compile("Claude" + "-Session", re.IGNORECASE)),
    ("a generated-with line", re.compile("Generated " + r"with \[?Claude", re.IGNORECASE)),
    ("a session link", re.compile(r"claude\.ai/" + "code", re.IGNORECASE)),
]

# Files the corpus workflow writes from public websites. They quote text from
# those sites (a contact address, a product name), so they are not scanned.
WRITTEN_BY_THE_CORPUS_WORKFLOW = {
    "docs/real-corpus/results/latest.json",
    "docs/real-corpus/report.html",
    "docs/real-corpus/scores.md",
}


def findings(text: str) -> list[tuple[str, str]]:
    """(label, matched text) for every pattern found in ``text``."""
    found = []
    for label, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            found.append((label, match.group(0)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a commit message for personal data and attribution lines.")
    parser.add_argument("--commit-message", type=Path, required=True, metavar="FILE",
                        help="the message file git passes to the commit-msg hook")
    args = parser.parse_args(argv)
    lines = args.commit_message.read_text(encoding="utf-8", errors="replace").splitlines()
    message = "\n".join(line for line in lines if not line.startswith("#"))
    found = findings(message)
    for label, text in found:
        print(f"commit message contains {label}: {text!r}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
