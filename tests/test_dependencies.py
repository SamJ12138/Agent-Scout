"""Declared dependencies and imports agree: everything declared is imported,
nothing imported is undeclared."""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_NAMES = {"pyyaml": "yaml", "beautifulsoup4": "bs4", "pillow": "PIL"}
LOCAL = {"agent_scout", "fixture_server", "run_corpus", "conftest", "make_demo_video", "demo", "score",
         "install_hooks", "hygiene"}


def requirement_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~ \[]", line)[0].lower())
    return names


def imported_modules(*directories: Path) -> set[str]:
    modules = set()
    for directory in directories:
        for path in directory.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
    return {m for m in modules if m not in sys.stdlib_module_names and m not in LOCAL}


def as_imports(names: set[str]) -> set[str]:
    return {IMPORT_NAMES.get(name, name) for name in names}


def test_requirements_txt_mirrors_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = {re.split(r"[<>=!~ \[]", item)[0].lower() for item in project["dependencies"]}
    assert declared == requirement_names(ROOT / "requirements.txt")


def test_runtime_imports_are_exactly_the_runtime_requirements():
    assert imported_modules(ROOT / "src") == as_imports(requirement_names(ROOT / "requirements.txt"))


def test_dev_requirements_are_all_used_and_cover_tests_and_scripts():
    runtime = as_imports(requirement_names(ROOT / "requirements.txt"))
    dev = as_imports(requirement_names(ROOT / "requirements-dev.txt"))
    used = imported_modules(ROOT / "tests", ROOT / "scripts")
    assert used <= runtime | dev, f"undeclared: {used - runtime - dev}"
    assert dev <= used, f"declared but never imported: {dev - used}"


def test_console_script_points_at_the_cli():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"] == {"agent-scout": "agent_scout.cli:main"}
    from agent_scout import __version__
    assert project["version"] == __version__
