"""Parsing of Playwright's machine-readable JSON report.

The project already produces an HTML report; the control centre additionally
enables the ``json`` reporter (via ``--reporter=list,html,json`` and
``PLAYWRIGHT_JSON_OUTPUT_NAME``) so results can be shown as structured data and
summarised for AI diagnosis instead of being scraped out of stdout. The HTML
report is untouched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from control_centre.paths import PROJECT_ROOT
from control_centre.redaction import redact

# Playwright test statuses, in the JSON reporter's vocabulary.
STATUS_EXPECTED = "expected"
STATUS_UNEXPECTED = "unexpected"
STATUS_FLAKY = "flaky"
STATUS_SKIPPED = "skipped"

# Playwright colourises error text; FORCE_COLOR=0 usually prevents it, but a
# report produced outside the control centre can still contain escape codes.
_ANSI_RE = re.compile("\u001b\\[[0-9;]*[A-Za-z]")


def _clean(text: str) -> str:
    return redact(_ANSI_RE.sub("", text or ""))


@dataclass
class StepTiming:
    title: str
    duration_ms: float
    error: str = ""


@dataclass
class Attachment:
    name: str
    content_type: str
    path: str = ""

    @property
    def kind(self) -> str:
        if self.content_type.startswith("image/"):
            return "screenshot"
        if self.content_type.startswith("video/"):
            return "video"
        if "zip" in self.content_type or self.name == "trace":
            return "trace"
        return "other"


@dataclass
class TestCase:
    title: str
    file: str
    project: str
    status: str  # expected | unexpected | flaky | skipped
    duration_ms: float = 0.0
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    steps: list[StepTiming] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == STATUS_EXPECTED

    @property
    def failed(self) -> bool:
        return self.status == STATUS_UNEXPECTED


@dataclass
class PlaywrightResults:
    json_path: str
    found: bool = False
    start_time: str = ""
    duration_ms: float = 0.0
    passed: int = 0
    failed: int = 0
    flaky: int = 0
    skipped: int = 0
    tests: list[TestCase] = field(default_factory=list)
    global_errors: list[str] = field(default_factory=list)
    html_report_dir: Path | None = None
    parse_error: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.flaky + self.skipped

    @property
    def all_passed(self) -> bool:
        return self.found and self.failed == 0 and self.passed > 0

    @property
    def failed_tests(self) -> list[TestCase]:
        return [t for t in self.tests if t.failed]

    def attachments_of(self, kind: str) -> list[Attachment]:
        return [a for test in self.tests for a in test.attachments if a.kind == kind]


def _walk_suites(suites: list[dict[str, Any]], file_hint: str = "") -> Iterator[tuple[dict[str, Any], str]]:
    for suite in suites or []:
        current_file = suite.get("file") or file_hint
        for spec in suite.get("specs", []) or []:
            yield spec, spec.get("file") or current_file
        yield from _walk_suites(suite.get("suites", []) or [], current_file)


def _collect_steps(steps: list[dict[str, Any]], depth: int = 0) -> list[StepTiming]:
    collected: list[StepTiming] = []
    for step in steps or []:
        title = ("  " * depth) + str(step.get("title", ""))
        collected.append(
            StepTiming(
                title=title,
                duration_ms=float(step.get("duration") or 0),
                error=_clean(str((step.get("error") or {}).get("message", ""))),
            )
        )
        if depth < 2:
            collected.extend(_collect_steps(step.get("steps", []) or [], depth + 1))
    return collected


def parse_playwright_results(
    json_path: str | Path, html_report_dir: str | Path | None = None
) -> PlaywrightResults:
    """Parse a Playwright JSON report; missing/unreadable files are reported."""
    path = Path(json_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    results = PlaywrightResults(json_path=str(json_path))

    if html_report_dir:
        html_dir = Path(html_report_dir)
        if not html_dir.is_absolute():
            html_dir = PROJECT_ROOT / html_dir
        if html_dir.exists():
            results.html_report_dir = html_dir

    if not path.exists():
        return results
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        results.parse_error = f"{type(exc).__name__}: {exc}"
        return results

    results.found = True
    stats = payload.get("stats") or {}
    results.start_time = str(stats.get("startTime", ""))
    results.duration_ms = float(stats.get("duration") or 0)
    results.passed = int(stats.get("expected") or 0)
    results.failed = int(stats.get("unexpected") or 0)
    results.flaky = int(stats.get("flaky") or 0)
    results.skipped = int(stats.get("skipped") or 0)
    results.global_errors = [
        _clean(str(err.get("message", err))) for err in (payload.get("errors") or [])
    ]

    for spec, spec_file in _walk_suites(payload.get("suites", []) or []):
        for test in spec.get("tests", []) or []:
            attempts = test.get("results", []) or []
            last = attempts[-1] if attempts else {}
            errors = [
                _clean(str(err.get("message", "")))
                for attempt in attempts
                for err in (attempt.get("errors") or [])
                if err.get("message")
            ]
            attachments = [
                Attachment(
                    name=str(att.get("name", "")),
                    content_type=str(att.get("contentType", "")),
                    path=str(att.get("path", "")),
                )
                for attempt in attempts
                for att in (attempt.get("attachments") or [])
                if att.get("path")
            ]
            results.tests.append(
                TestCase(
                    title=str(spec.get("title", "")),
                    file=str(spec_file),
                    project=str(test.get("projectName", "")),
                    status=str(test.get("status", "")),
                    duration_ms=float(sum(float(a.get("duration") or 0) for a in attempts)),
                    retries=max(0, len(attempts) - 1),
                    errors=errors,
                    steps=_collect_steps(last.get("steps", []) or []),
                    attachments=attachments,
                )
            )
    return results


def summarise_for_diagnosis(results: PlaywrightResults) -> dict[str, Any]:
    """Compact, redacted summary for the LLM diagnosis payload."""
    return {
        "total": results.total,
        "passed": results.passed,
        "failed": results.failed,
        "flaky": results.flaky,
        "skipped": results.skipped,
        "duration_ms": results.duration_ms,
        "tests": [
            {
                "title": t.title,
                "file": Path(t.file).name,
                "status": t.status,
                "duration_ms": round(t.duration_ms),
                "retries": t.retries,
                "errors": [e[:400] for e in t.errors[:3]],
                "slowest_steps": [
                    {"title": s.title.strip(), "duration_ms": round(s.duration_ms)}
                    for s in sorted(t.steps, key=lambda s: s.duration_ms, reverse=True)[:5]
                ],
            }
            for t in results.tests
        ],
        "global_errors": [e[:400] for e in results.global_errors[:5]],
    }
