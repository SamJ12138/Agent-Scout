"""Write the outputs of a run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import obs


def write_json(results: dict[str, Any], out_dir: Path) -> Path:
    path = Path(out_dir) / "results.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def write_all(results: dict[str, Any], out_dir: Path) -> list[Path]:
    """Write every report into ``out_dir`` and return the paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for writer in (write_json,):
        with obs.span("report", file=writer.__name__) as span:
            path = writer(results, out_dir)
            span.context["bytes"] = path.stat().st_size
            paths.append(path)
    return paths
