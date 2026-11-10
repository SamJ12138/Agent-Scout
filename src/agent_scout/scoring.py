"""Compare a results.json with hand-written ground truth, field by field.

Outcomes
    match     the tool's value equals the reference after normalisation.
              Both "unknown" is a match: the site does not say, and the tool
              did not claim anything.
    partial   the tool is partly right:
              - list fields: the two sets share at least one value but differ;
              - one_liner: one text contains the other, or at least half of
                their distinct words are shared (Jaccard >= 0.5);
              - pricing: at least one sub-value (free_tier, starting_price)
                that the reference knows is matched, and another is not;
              - hq_location: the country matches and the city does not, or the
                city matches and the country is absent.
    mismatch  the tool states a value and none of it agrees with the
              reference. This includes a value where the reference says the
              site does not state one.
    missing   the reference has a value and the tool reports unknown.

Normalisation: case and surrounding whitespace are ignored everywhere; list
fields are compared as sets; prices are compared by currency, amount and
period ("$49/mo" = "$49 per month"); country spellings are unified ("USA" =
"United States"). A ground-truth entry may carry ``also_acceptable``: a list of
alternative values, each of which is scored and the best outcome kept. Other
unknown keys in a ground-truth file are ignored.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import obs
from .geo import country_name
from .model import FIELDS, LIST_FIELDS, UNKNOWN

OUTCOMES = ("match", "partial", "mismatch", "missing")
_RANK = {"match": 0, "partial": 1, "missing": 2, "mismatch": 3}


@dataclass
class Outcome:
    outcome: str
    detail: str = ""


def _text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def _words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _text(value)))


def _is_unknown(value: Any) -> bool:
    if value is None or value == [] or value == {}:
        return True
    if isinstance(value, str):
        return _text(value) in ("unknown", "")
    if isinstance(value, dict):
        return all(_is_unknown(v) for v in value.values())
    return False


def normalise_price(value: Any) -> str:
    """'$49 / mo' -> '$49/month'. Unrecognised text is returned lower-cased."""
    text = _text(value).replace("us$", "$")
    match = re.search(r"([$€£])\s?(\d[\d,]*(?:\.\d+)?)", text)
    if not match:
        return text
    amount = float(match.group(2).replace(",", ""))
    rest = text[match.end():]
    unit = re.search(r"\b(user|seat|member|agent|editor|workspace|account)\b", rest)
    period = re.search(r"\b(month|mo|monthly|year|yr|annum|annually|yearly|week)\b", rest)
    names = {"mo": "month", "monthly": "month", "yr": "year", "annum": "year", "annually": "year",
             "yearly": "year"}
    parts = [f"{match.group(1)}{amount:g}"]
    if unit:
        parts.append(unit.group(1))
    if period:
        parts.append(names.get(period.group(1), period.group(1)))
    return "/".join(parts)


def _country(value: Any) -> str:
    return _text(country_name(str(value), allow_code=True) or value)


def _compare_scalar(truth: Any, got: Any) -> Outcome:
    same = truth == got if isinstance(truth, bool) or isinstance(got, bool) else _text(truth) == _text(got)
    return Outcome("match" if same else "mismatch", "" if same else f"expected {truth!r}, got {got!r}")


def _compare_one_liner(truth: str, got: str) -> Outcome:
    a, b = _text(truth).strip(" .\"'"), _text(got).strip(" .\"'")
    if a == b:
        return Outcome("match")
    wa, wb = _words(a), _words(b)
    jaccard = len(wa & wb) / len(wa | wb) if wa | wb else 0.0
    if a in b or b in a or jaccard >= 0.5:
        return Outcome("partial", f"word overlap {jaccard:.2f}")
    return Outcome("mismatch", f"word overlap {jaccard:.2f}")


def _compare_list(truth: list, got: list) -> Outcome:
    a, b = {_text(v) for v in truth}, {_text(v) for v in got}
    if a == b:
        return Outcome("match")
    detail = f"{len(a & b)} of {len(a)} found, {len(b - a)} extra"
    return Outcome("partial" if a & b else "mismatch", detail)


def _sub(value: Any, key: str) -> Any:
    return value.get(key, UNKNOWN) if isinstance(value, dict) else UNKNOWN


def _compare_parts(pairs: list[tuple[str, Any, Any, bool]]) -> Outcome:
    """pairs: (name, truth, got, equal). Unknown-vs-unknown parts earn nothing."""
    right = [name for name, truth, got, equal in pairs if equal and not _is_unknown(truth)]
    wrong = [name for name, truth, got, equal in pairs if not equal]
    if not wrong:
        return Outcome("match")
    detail = "differs: " + ", ".join(wrong)
    return Outcome("partial" if right else "mismatch", detail)


def _compare_pricing(truth: Any, got: Any) -> Outcome:
    pairs = []
    for key in ("free_tier", "starting_price"):
        t, g = _sub(truth, key), _sub(got, key)
        if _is_unknown(t) or _is_unknown(g):
            equal = _is_unknown(t) and _is_unknown(g)
        elif key == "starting_price":
            equal = normalise_price(t) == normalise_price(g)
        else:
            equal = t == g
        pairs.append((key, t, g, equal))
    return _compare_parts(pairs)


def _compare_hq(truth: Any, got: Any) -> Outcome:
    pairs = []
    for key in ("city", "country"):
        t, g = _sub(truth, key), _sub(got, key)
        if _is_unknown(t) or _is_unknown(g):
            equal = _is_unknown(t) and _is_unknown(g)
        else:
            equal = (_country(t) == _country(g)) if key == "country" else (_text(t) == _text(g))
        pairs.append((key, t, g, equal))
    return _compare_parts(pairs)


def compare(field_name: str, truth: Any, got: Any) -> Outcome:
    """Score one field of one site. See the module docstring for the rules."""
    if _is_unknown(truth) and _is_unknown(got):
        return Outcome("match")
    if _is_unknown(got):
        return Outcome("missing")
    if _is_unknown(truth):
        return Outcome("mismatch", "reference says the site does not state this")
    if field_name in LIST_FIELDS:
        truth_list = truth if isinstance(truth, list) else [truth]
        got_list = got if isinstance(got, list) else [got]
        return _compare_list(truth_list, got_list)
    if field_name == "one_liner":
        return _compare_one_liner(truth, got)
    if field_name == "pricing":
        return _compare_pricing(truth, got)
    if field_name == "hq_location":
        return _compare_hq(truth, got)
    return _compare_scalar(truth, got)


def compare_entry(field_name: str, entry: Any, got: Any) -> Outcome:
    """Score against a ground-truth entry, honouring ``also_acceptable``."""
    if not isinstance(entry, dict):
        entry = {"value": entry}
    candidates = [entry.get("value", UNKNOWN)]
    extra = entry.get("also_acceptable")
    if isinstance(extra, list):
        candidates.extend(extra)
    elif extra is not None:
        candidates.append(extra)
    outcomes = [compare(field_name, candidate, got) for candidate in candidates]
    return min(outcomes, key=lambda outcome: _RANK[outcome.outcome])


@dataclass
class SiteScore:
    slug: str
    name: str
    status: str
    outcomes: dict[str, Outcome] = field(default_factory=dict)


@dataclass
class RunScore:
    sites: dict[str, SiteScore] = field(default_factory=dict)
    unscored_results: list[str] = field(default_factory=list)   # result sites without ground truth
    unscored_truth: list[str] = field(default_factory=list)     # ground truth without a result

    def totals(self) -> dict[str, int]:
        counts = {name: 0 for name in OUTCOMES}
        for site in self.sites.values():
            for outcome in site.outcomes.values():
                counts[outcome.outcome] += 1
        return counts

    def field_totals(self) -> dict[str, dict[str, int]]:
        table = {name: {o: 0 for o in OUTCOMES} for name in FIELDS}
        for site in self.sites.values():
            for name, outcome in site.outcomes.items():
                table[name][outcome.outcome] += 1
        return table

    def all_match(self) -> bool:
        totals = self.totals()
        return (bool(self.sites) and not self.unscored_results and not self.unscored_truth
                and totals["match"] == sum(totals.values()))

    def table(self) -> str:
        """Plain-text table: one row per site, one column per field."""
        width = max([len(slug) for slug in self.sites] + [4])
        short = {"one_liner": "one_liner", "categories": "categories", "target_user": "target", "tasks": "tasks",
                 "can_execute": "executes", "multi_agent": "multi", "integrations": "integr", "pricing": "pricing",
                 "hq_location": "hq"}
        lines = [f"{'site':<{width}}  {'status':<17} " + " ".join(f"{short[name]:<10}" for name in FIELDS)]
        for slug, site in self.sites.items():
            cells = " ".join(f"{site.outcomes[name].outcome:<10}" for name in FIELDS)
            lines.append(f"{slug:<{width}}  {site.status:<17} {cells}")
        totals = self.totals()
        lines.append("")
        lines.append("totals: " + ", ".join(f"{totals[name]} {name}" for name in OUTCOMES)
                     + f" (of {sum(totals.values())} site-fields)")
        for slug in self.unscored_results:
            lines.append(f"no ground truth for result site: {slug}")
        for slug in self.unscored_truth:
            lines.append(f"no result for ground-truth site: {slug}")
        return "\n".join(lines) + "\n"

    def markdown(self) -> str:
        """Markdown: per-site table, per-field table, notes on partial/mismatch."""
        lines = ["| site | status | " + " | ".join(FIELDS) + " |", "|---|---|" + "---|" * len(FIELDS)]
        for slug, site in self.sites.items():
            lines.append(f"| {slug} | {site.status} | "
                         + " | ".join(site.outcomes[name].outcome for name in FIELDS) + " |")
        lines += ["", "| field | " + " | ".join(OUTCOMES) + " |", "|---|" + "---|" * len(OUTCOMES)]
        for name, counts in self.field_totals().items():
            lines.append(f"| {name} | " + " | ".join(str(counts[o]) for o in OUTCOMES) + " |")
        totals = self.totals()
        lines += ["", "Totals: " + ", ".join(f"{totals[name]} {name}" for name in OUTCOMES)
                  + f" (of {sum(totals.values())} site-fields)."]
        notes = [f"- {slug} / {name}: {outcome.outcome} ({outcome.detail})"
                 for slug, site in self.sites.items() for name, outcome in site.outcomes.items()
                 if outcome.outcome != "match" and outcome.detail]
        if notes:
            lines += ["", "Details:", *notes]
        for slug in self.unscored_results:
            lines.append(f"- no ground truth for result site: {slug}")
        for slug in self.unscored_truth:
            lines.append(f"- no result for ground-truth site: {slug}")
        return "\n".join(lines) + "\n"


def _host(url: str) -> str:
    host = (urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def load_ground_truth(directory: Path) -> dict[str, dict]:
    """slug -> ground-truth document, for every site file in ``directory``."""
    truth: dict[str, dict] = {}
    for path in sorted(Path(directory).glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            obs.emit("report", "skip", error_type="ground_truth_invalid", path=path.name)
            continue
        if isinstance(doc, dict) and isinstance(doc.get("fields"), dict):
            truth[str(doc.get("slug") or path.stem)] = doc
    return truth


def score_results(results: dict, ground_truth_dir: Path) -> RunScore:
    truth = load_ground_truth(ground_truth_dir)
    by_host = {_host(doc.get("url", "")): slug for slug, doc in truth.items() if _host(doc.get("url", ""))}
    score = RunScore()
    used: set[str] = set()
    for site in results.get("sites", []):
        slug = site["slug"] if site["slug"] in truth else (
            by_host.get(_host(site.get("url", ""))) or by_host.get(_host(site.get("final_url") or "")))
        if slug is None or slug in used:
            score.unscored_results.append(site["slug"])
            continue
        used.add(slug)
        doc = truth[slug]
        site_score = SiteScore(slug=slug, name=site.get("name") or doc.get("name") or slug, status=site["status"])
        for name in FIELDS:
            got = site["fields"].get(name, {}).get("value", UNKNOWN)
            site_score.outcomes[name] = compare_entry(name, doc["fields"].get(name, {"value": UNKNOWN}), got)
        score.sites[slug] = site_score
    score.unscored_truth = [slug for slug in truth if slug not in used]
    return score
