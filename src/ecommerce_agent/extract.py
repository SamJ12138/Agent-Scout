"""Extract structured fields from product data."""

from typing import Any
from .logger import log


def extract_fields(product_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract structured fields from raw product data.
    
    In production, this would use NLP/LLM for intelligent extraction.
    For demo, we do simple field mapping and inference.
    """
    log.info(f"Extracting fields from: {product_data.get('name', 'unknown')}")
    
    raw_text = product_data.get("description", "")
    
    # Demo extraction logic (would be smarter in production)
    extracted = {
        "product_one_liner": _extract_one_liner(product_data),
        "target_user": _infer_target_user(raw_text),
        "tasks_covered": _extract_tasks(product_data),
        "can_execute": _check_execution_capability(raw_text),
        "multi_agent": _check_multi_agent(raw_text),
        "integrations": product_data.get("integrations", []),
        "evidence_sources": [product_data.get("url", "mock://source")],
        "location": product_data.get("location", "Unknown"),
    }
    
    log.debug(f"Extracted {len(extracted)} fields")
    return extracted


def _extract_one_liner(data: dict[str, Any]) -> str:
    """Generate a one-liner summary."""
    name = data.get("name", "Product")
    category = data.get("category", "tool")
    return f"{name}: A {category} for automated workflows."


def _infer_target_user(text: str) -> str:
    """Infer target user from description."""
    text_lower = text.lower()
    if "developer" in text_lower or "api" in text_lower:
        return "Developers"
    if "business" in text_lower or "enterprise" in text_lower:
        return "Business users"
    if "researcher" in text_lower:
        return "Researchers"
    return "General users"


def _extract_tasks(data: dict[str, Any]) -> list[str]:
    """Extract covered tasks."""
    return data.get("tasks", ["data extraction", "report generation"])


def _check_execution_capability(text: str) -> bool:
    """Check if product can execute actions."""
    keywords = ["automate", "execute", "run", "perform", "action"]
    return any(kw in text.lower() for kw in keywords)


def _check_multi_agent(text: str) -> bool:
    """Check for multi-agent capability."""
    keywords = ["multi-agent", "multiple agents", "agent swarm", "collaborative"]
    return any(kw in text.lower() for kw in keywords)
