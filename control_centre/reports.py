"""Serving, packaging and opening generated reports.

Locust writes a single self-contained HTML file; Playwright writes a directory.
Both are read back from ``results/<run-id>/`` only -- ``ensure_inside`` is
applied to every path before it is opened, zipped or streamed to the browser,
so a manipulated manifest cannot make the app read outside the results tree.
"""

from __future__ import annotations

import io
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path

from control_centre.commands import build_show_report_argv, build_show_trace_argv
from control_centre.paths import RESULTS_DIR, ensure_inside
from control_centre.process import spawn_detached

# Embedding a very large HTML report in an iframe is slow and often blank.
MAX_EMBED_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class DownloadPayload:
    file_name: str
    data: bytes
    mime: str


def safe_path(candidate: str | Path | None) -> Path | None:
    """Resolve a results-relative path, or ``None`` when it escapes/does not exist."""
    if not candidate:
        return None
    try:
        path = ensure_inside(candidate, RESULTS_DIR)
    except ValueError:
        return None
    return path if path.exists() else None


def can_embed(path: Path | None) -> bool:
    return bool(path and path.is_file() and path.stat().st_size <= MAX_EMBED_BYTES)


def read_bytes(path: Path | None) -> bytes | None:
    if path is None or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def html_download(path: Path | None) -> DownloadPayload | None:
    data = read_bytes(path)
    if data is None or path is None:
        return None
    return DownloadPayload(path.name, data, "text/html")


def csv_downloads(csv_prefix: str | Path | None) -> list[DownloadPayload]:
    """Every CSV Locust produced for a prefix, ready for download buttons."""
    if not csv_prefix:
        return []
    try:
        base = ensure_inside(csv_prefix, RESULTS_DIR)
    except ValueError:
        return []
    payloads: list[DownloadPayload] = []
    for suffix in ("_stats.csv", "_failures.csv", "_exceptions.csv", "_stats_history.csv"):
        candidate = base.with_name(base.name + suffix)
        data = read_bytes(candidate)
        if data is not None:
            payloads.append(DownloadPayload(candidate.name, data, "text/csv"))
    return payloads


def zip_directory(directory: str | Path | None, archive_name: str = "report.zip") -> DownloadPayload | None:
    """Zip a report directory in memory (Playwright's HTML report is multi-file)."""
    path = safe_path(directory)
    if path is None or not path.is_dir():
        return None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(path.rglob("*")):
            if item.is_file():
                archive.write(item, item.relative_to(path).as_posix())
    return DownloadPayload(archive_name, buffer.getvalue(), "application/zip")


def open_in_browser(path: str | Path | None) -> bool:
    """Open a local report file in the default browser (local-only convenience)."""
    resolved = safe_path(path)
    if resolved is None:
        return False
    return webbrowser.open(resolved.as_uri())


def launch_playwright_report(html_report_dir: str | Path | None) -> int | None:
    """Start ``npx playwright show-report <dir>`` as a detached helper process."""
    resolved = safe_path(html_report_dir)
    if resolved is None or not resolved.is_dir():
        return None
    return spawn_detached(build_show_report_argv(resolved))


def launch_trace_viewer(trace_path: str | Path | None) -> int | None:
    resolved = safe_path(trace_path)
    if resolved is None:
        return None
    return spawn_detached(build_show_trace_argv(resolved))


def list_artifacts(directory: str | Path | None, suffixes: tuple[str, ...]) -> list[Path]:
    """Screenshots/videos/traces produced inside a run's output directory."""
    path = safe_path(directory)
    if path is None or not path.is_dir():
        return []
    return sorted(p for p in path.rglob("*") if p.suffix.lower() in suffixes)
