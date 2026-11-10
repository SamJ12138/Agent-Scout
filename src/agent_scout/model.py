"""The result data model shared by extraction, reports and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

UNKNOWN = "unknown"
SCHEMA_VERSION = "1.0"

FIELDS = ("one_liner", "categories", "target_user", "tasks", "can_execute", "multi_agent",
          "integrations", "pricing", "hq_location")
LIST_FIELDS = ("categories", "target_user", "tasks", "integrations")
METHODS = ("meta", "json-ld", "heading", "sentence", "link", "table", "llm")

FIELD_LABELS = {
    "one_liner": "One-liner",
    "categories": "Categories",
    "target_user": "Target users",
    "tasks": "Tasks",
    "can_execute": "Acts by itself",
    "multi_agent": "Multi-agent",
    "integrations": "Integrations",
    "pricing": "Pricing",
    "hq_location": "Headquarters",
}


@dataclass
class Evidence:
    url: str                 # page the quote was read on
    quote: str               # verbatim text (whitespace collapsed)
    method: str              # one of METHODS
    item: str | None = None  # list item or sub-value ("free_tier", "city") the quote supports

    def as_dict(self) -> dict[str, Any]:
        return {"item": self.item, "url": self.url, "quote": self.quote, "method": self.method}


@dataclass
class FieldResult:
    value: Any = UNKNOWN
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.value != UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "evidence": [e.as_dict() for e in self.evidence]}


def unknown_fields() -> dict[str, FieldResult]:
    return {name: FieldResult() for name in FIELDS}
