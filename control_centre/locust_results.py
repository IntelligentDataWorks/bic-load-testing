"""Parsing of Locust's CSV output.

Locust writes ``<prefix>_stats.csv``, ``<prefix>_failures.csv``,
``<prefix>_exceptions.csv`` and ``<prefix>_stats_history.csv``. The stats file's
percentile columns are bucketed by Locust itself, so a run with a handful of
samples reports percentiles that are all the same rounded number -- the parser
flags that rather than presenting it as a meaningful distribution.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from control_centre.paths import PROJECT_ROOT

# Below this many requests, percentiles say almost nothing.
SMALL_SAMPLE_THRESHOLD = 20


def _to_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text not in {"", "N/A"} else None
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else 0


@dataclass
class EndpointStats:
    """One row of ``<prefix>_stats.csv``."""

    method: str
    name: str
    request_count: int = 0
    failure_count: int = 0
    median_ms: float | None = None
    average_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    avg_content_bytes: float | None = None
    requests_per_second: float | None = None
    failures_per_second: float | None = None
    percentiles: dict[str, float | None] = field(default_factory=dict)

    @property
    def is_aggregated(self) -> bool:
        return self.name.strip().lower() == "aggregated"

    @property
    def failure_pct(self) -> float:
        return (self.failure_count / self.request_count * 100) if self.request_count else 0.0

    def p(self, key: str) -> float | None:
        return self.percentiles.get(key)


@dataclass
class FailureRow:
    method: str
    name: str
    error: str
    occurrences: int


@dataclass
class ExceptionRow:
    count: int
    message: str
    traceback: str
    nodes: str


@dataclass
class HistoryPoint:
    timestamp: int | None
    user_count: int
    requests_per_second: float | None
    failures_per_second: float | None
    p50_ms: float | None
    p95_ms: float | None


@dataclass
class LocustResults:
    """Everything parsed out of one Locust CSV prefix."""

    prefix: str
    found: bool = False
    endpoints: list[EndpointStats] = field(default_factory=list)
    failures: list[FailureRow] = field(default_factory=list)
    exceptions: list[ExceptionRow] = field(default_factory=list)
    history: list[HistoryPoint] = field(default_factory=list)
    html_report: Path | None = None
    parse_errors: list[str] = field(default_factory=list)

    @property
    def aggregated(self) -> EndpointStats | None:
        return next((e for e in self.endpoints if e.is_aggregated), None)

    @property
    def per_endpoint(self) -> list[EndpointStats]:
        return [e for e in self.endpoints if not e.is_aggregated]

    @property
    def total_requests(self) -> int:
        agg = self.aggregated
        return agg.request_count if agg else sum(e.request_count for e in self.per_endpoint)

    @property
    def total_failures(self) -> int:
        agg = self.aggregated
        return agg.failure_count if agg else sum(e.failure_count for e in self.per_endpoint)

    @property
    def failure_pct(self) -> float:
        return (self.total_failures / self.total_requests * 100) if self.total_requests else 0.0

    @property
    def small_sample(self) -> bool:
        return 0 < self.total_requests < SMALL_SAMPLE_THRESHOLD

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock span covered by the history file, when it has one."""
        stamps = [h.timestamp for h in self.history if h.timestamp]
        if len(stamps) < 2:
            return None
        return float(max(stamps) - min(stamps))

    @property
    def peak_users(self) -> int:
        return max((h.user_count for h in self.history), default=0)


_PERCENTILE_KEYS = ("50%", "66%", "75%", "80%", "90%", "95%", "98%", "99%", "99.9%", "99.99%", "100%")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_locust_results(csv_prefix: str | Path, html_report: str | Path | None = None) -> LocustResults:
    """Parse every CSV Locust wrote for ``csv_prefix``.

    ``csv_prefix`` is the value passed to ``locust --csv`` (project-relative or
    absolute); missing files are reported, not raised.
    """
    prefix_path = Path(csv_prefix)
    if not prefix_path.is_absolute():
        prefix_path = PROJECT_ROOT / prefix_path
    results = LocustResults(prefix=str(csv_prefix))

    stats_file = prefix_path.with_name(prefix_path.name + "_stats.csv")
    if stats_file.exists():
        results.found = True
        try:
            for row in _read_csv(stats_file):
                results.endpoints.append(
                    EndpointStats(
                        method=(row.get("Type") or "").strip(),
                        name=(row.get("Name") or "").strip(),
                        request_count=_to_int(row.get("Request Count")),
                        failure_count=_to_int(row.get("Failure Count")),
                        median_ms=_to_float(row.get("Median Response Time")),
                        average_ms=_to_float(row.get("Average Response Time")),
                        min_ms=_to_float(row.get("Min Response Time")),
                        max_ms=_to_float(row.get("Max Response Time")),
                        avg_content_bytes=_to_float(row.get("Average Content Size")),
                        requests_per_second=_to_float(row.get("Requests/s")),
                        failures_per_second=_to_float(row.get("Failures/s")),
                        percentiles={key: _to_float(row.get(key)) for key in _PERCENTILE_KEYS},
                    )
                )
        except (OSError, csv.Error) as exc:
            results.parse_errors.append(f"{stats_file.name}: {exc}")

    failures_file = prefix_path.with_name(prefix_path.name + "_failures.csv")
    if failures_file.exists():
        try:
            for row in _read_csv(failures_file):
                results.failures.append(
                    FailureRow(
                        method=(row.get("Method") or "").strip(),
                        name=(row.get("Name") or "").strip(),
                        error=(row.get("Error") or "").strip(),
                        occurrences=_to_int(row.get("Occurrences")),
                    )
                )
        except (OSError, csv.Error) as exc:
            results.parse_errors.append(f"{failures_file.name}: {exc}")

    exceptions_file = prefix_path.with_name(prefix_path.name + "_exceptions.csv")
    if exceptions_file.exists():
        try:
            for row in _read_csv(exceptions_file):
                results.exceptions.append(
                    ExceptionRow(
                        count=_to_int(row.get("Count")),
                        message=(row.get("Message") or "").strip(),
                        traceback=(row.get("Traceback") or "").strip(),
                        nodes=(row.get("Nodes") or "").strip(),
                    )
                )
        except (OSError, csv.Error) as exc:
            results.parse_errors.append(f"{exceptions_file.name}: {exc}")

    history_file = prefix_path.with_name(prefix_path.name + "_stats_history.csv")
    if history_file.exists():
        try:
            for row in _read_csv(history_file):
                if (row.get("Name") or "").strip().lower() != "aggregated":
                    continue
                results.history.append(
                    HistoryPoint(
                        timestamp=_to_int(row.get("Timestamp")) or None,
                        user_count=_to_int(row.get("User Count")),
                        requests_per_second=_to_float(row.get("Requests/s")),
                        failures_per_second=_to_float(row.get("Failures/s")),
                        p50_ms=_to_float(row.get("50%")),
                        p95_ms=_to_float(row.get("95%")),
                    )
                )
        except (OSError, csv.Error) as exc:
            results.parse_errors.append(f"{history_file.name}: {exc}")

    if html_report:
        candidate = Path(html_report)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if candidate.exists():
            results.html_report = candidate
            results.found = True

    return results


def summarise_for_diagnosis(results: LocustResults) -> dict[str, Any]:
    """Compact, non-sensitive summary for the LLM diagnosis payload."""
    agg = results.aggregated
    summary: dict[str, Any] = {
        "total_requests": results.total_requests,
        "total_failures": results.total_failures,
        "failure_pct": round(results.failure_pct, 3),
        "small_sample": results.small_sample,
        "peak_users": results.peak_users,
        "duration_seconds": results.duration_seconds,
    }
    if agg:
        summary["aggregate"] = {
            "avg_ms": agg.average_ms,
            "median_ms": agg.median_ms,
            "min_ms": agg.min_ms,
            "max_ms": agg.max_ms,
            "rps": agg.requests_per_second,
            "p90_ms": agg.p("90%"),
            "p95_ms": agg.p("95%"),
            "p99_ms": agg.p("99%"),
        }
    summary["endpoints"] = [
        {
            "method": e.method,
            "name": e.name,
            "requests": e.request_count,
            "failures": e.failure_count,
            "failure_pct": round(e.failure_pct, 3),
            "avg_ms": e.average_ms,
            "p95_ms": e.p("95%"),
            "max_ms": e.max_ms,
        }
        for e in results.per_endpoint
    ]
    summary["failures"] = [
        {"method": f.method, "name": f.name, "error": f.error[:300], "occurrences": f.occurrences}
        for f in results.failures[:20]
    ]
    summary["exceptions"] = [
        {"count": e.count, "message": e.message[:300]} for e in results.exceptions[:10]
    ]
    return summary
