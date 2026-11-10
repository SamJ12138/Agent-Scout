"""Report generation and output writing."""

import json
from pathlib import Path
from typing import Any
from datetime import datetime
from .logger import log


def generate_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a structured report from extraction results."""
    log.info(f"Generating report for {len(results)} products")
    
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "product_count": len(results),
            "version": "1.0",
        },
        "products": results,
        "summary": _generate_summary(results),
    }
    
    return report


def _generate_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate summary statistics."""
    if not results:
        return {"total": 0}
    
    return {
        "total": len(results),
        "can_execute_count": sum(1 for r in results if r.get("can_execute")),
        "multi_agent_count": sum(1 for r in results if r.get("multi_agent")),
        "unique_integrations": list(set(
            intg for r in results for intg in r.get("integrations", [])
        )),
    }


def write_report(report: dict[str, Any], output_path: Path) -> Path:
    """Write report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    log.info(f"Report written to: {output_path}")
    return output_path
