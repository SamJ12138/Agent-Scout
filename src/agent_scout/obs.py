"""Structured run log: one JSON object per line, one line per event.

Every event has the same keys:

    ts           ISO-8601 UTC timestamp, millisecond precision
    run_id       identifier shared by every event of one run
    site         slug of the site the event belongs to, or null
    stage        input | robots | fetch | parse | extract | llm | report | run
    event        start | success | fail | skip
    duration_ms  integer for the closing event of a span, otherwise null
    error_type   short machine-readable reason for fail/skip, otherwise null
    context      free-form details (url, status, bytes, encoding, field, method, ...)

Modules call the module-level ``emit`` / ``span`` helpers, which write to the
log of the current run and do nothing when no run is active (unit tests).
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

EVENTS = ("start", "success", "fail", "skip")
REDACTED = "[redacted]"


class LogFormatError(Exception):
    """The file given to report-log is not an Agent Scout run log."""


class Span:
    """Handle yielded by ``EventLog.span``: add context, or mark fail/skip."""

    def __init__(self, context: dict[str, Any]):
        self.context = context
        self.outcome = "success"
        self.error_type: str | None = None

    def fail(self, error_type: str, **context: Any) -> None:
        self.outcome, self.error_type = "fail", error_type
        self.context.update(context)

    def skip(self, error_type: str, **context: Any) -> None:
        self.outcome, self.error_type = "skip", error_type
        self.context.update(context)


class EventLog:
    def __init__(self, path: Path | None, run_id: str,
                 perf: Callable[[], float] = time.perf_counter):
        self.path = Path(path) if path is not None else None
        self.run_id = run_id
        self._perf = perf
        self._secrets: list[str] = []
        self._file = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8", newline="\n")

    def register_secret(self, secret: str | None) -> None:
        """Any occurrence of ``secret`` in later events is replaced before writing."""
        if secret:
            self._secrets.append(secret)

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, REDACTED)
            return value
        if isinstance(value, dict):
            return {str(k): self._scrub(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._scrub(v) for v in value]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return self._scrub(str(value))

    def emit(self, stage: str, event: str, *, site: str | None = None,
             duration_ms: int | None = None, error_type: str | None = None,
             **context: Any) -> None:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}; expected one of {EVENTS}")
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": self.run_id,
            "site": site,
            "stage": stage,
            "event": event,
            "duration_ms": duration_ms,
            "error_type": self._scrub(error_type),
            "context": self._scrub(context),
        }
        if self._file is not None:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()

    @contextmanager
    def span(self, stage: str, *, site: str | None = None, **context: Any) -> Iterator[Span]:
        """Emit ``start`` now and ``success`` / ``fail`` / ``skip`` with a duration on exit."""
        self.emit(stage, "start", site=site, **context)
        span = Span(dict(context))
        began = self._perf()
        try:
            yield span
        except BaseException as exc:
            self.emit(stage, "fail", site=site, duration_ms=self._elapsed(began),
                      error_type=type(exc).__name__, **span.context)
            raise
        self.emit(stage, span.outcome, site=site, duration_ms=self._elapsed(began),
                  error_type=span.error_type, **span.context)

    def _elapsed(self, began: float) -> int:
        return int(round((self._perf() - began) * 1000))

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


_current: EventLog | None = None
_null = EventLog(None, run_id="none")


def set_current(log: EventLog | None) -> None:
    global _current
    _current = log


def current() -> EventLog:
    return _current if _current is not None else _null


def emit(stage: str, event: str, **kwargs: Any) -> None:
    current().emit(stage, event, **kwargs)


def span(stage: str, **kwargs: Any):
    return current().span(stage, **kwargs)


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{int(time.time_ns()) % 0xFFFF:04x}"


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: the smallest value with at least pct% of values <= it."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without importing math
    return ordered[int(rank) - 1]


def read_events(path: Path) -> list[dict[str, Any]]:
    events = []
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                emit("report", "fail", error_type="log_format", line=number)
                raise LogFormatError(f"{path}: line {number} is not JSON") from None
            if not isinstance(record, dict) or "stage" not in record or "event" not in record:
                raise LogFormatError(f"{path}: line {number} is not an Agent Scout event")
            events.append(record)
    return events


def report_log(path: Path) -> str:
    """Text summary of a run log: stage x error_type counts and per-stage p50/p95."""
    events = read_events(path)
    errors: Counter[tuple[str, str, str]] = Counter()
    durations: dict[str, list[float]] = defaultdict(list)
    for record in events:
        if record["event"] in ("fail", "skip"):
            errors[(record["stage"], str(record.get("error_type") or "unspecified"), record["event"])] += 1
        if record["event"] != "start" and isinstance(record.get("duration_ms"), (int, float)):
            durations[record["stage"]].append(record["duration_ms"])

    lines = [f"{len(events)} events in {Path(path).name}", ""]
    lines.append("Failures and skips (stage x error_type)")
    lines.append(f"{'stage':<10} {'error_type':<28} {'event':<6} {'count':>5}")
    if not errors:
        lines.append("(none recorded)")
    for (stage, error_type, event), count in sorted(errors.items()):
        lines.append(f"{stage:<10} {error_type:<28} {event:<6} {count:>5}")
    lines.append("")
    lines.append("Durations in ms (events that carry a duration)")
    lines.append(f"{'stage':<10} {'n':>5} {'p50':>8} {'p95':>8}")
    for stage in sorted(durations):
        values = durations[stage]
        lines.append(f"{stage:<10} {len(values):>5} {percentile(values, 50):>8g} {percentile(values, 95):>8g}")
    return "\n".join(lines) + "\n"
