"""Make git run scripts/hooks/pre-commit (the test suite) before every commit.

    python scripts/install_hooks.py

Sets core.hooksPath for this clone to scripts/hooks. Undo with
`git config --unset core.hooksPath`.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = "scripts/hooks"


def install(repo: Path = ROOT) -> int:
    hook = repo / HOOKS / "pre-commit"
    if not hook.is_file():
        print(f"install_hooks: {hook} is missing", file=sys.stderr)
        return 1
    if os.name != "nt":
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    done = subprocess.run(["git", "config", "core.hooksPath", HOOKS], cwd=repo, capture_output=True, text=True)
    if done.returncode != 0:
        print(f"install_hooks: git config failed: {done.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"git will now run {HOOKS}/pre-commit before each commit in {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(install())
