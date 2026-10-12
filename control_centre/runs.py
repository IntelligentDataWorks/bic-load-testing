"""Run identity, isolated result directories and the on-disk run manifest.

Every execution gets ``results/<run-id>/`` of its own, so a new run can never
overwrite an earlier one's CSV/HTML output. The manifest stores what the run
was and where its artefacts landed -- configuration, timings, status, exit code
and a redacted command -- and never stores a secret.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from control_centre.models import RunStatus, TestArea
from control_centre.paths import RESULTS_DIR, ensure_inside, relative_to_root

MANIFEST_NAME = "manifest.json"
LOG_NAME = "run.log"
_RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[a-z_]+-[0-9a-f]{6}$")


def new_run_id(area: TestArea) -> str:
    """Sortable, collision-proof run id: ``20260922-140355-serving_endpoint-9f3ac1``."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{area.value}-{uuid.uuid4().hex[:6]}"


def is_valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID_RE.fullmatch(run_id or ""))


def run_dir(run_id: str, create: bool = False) -> Path:
    """Directory for a run, guaranteed to sit inside ``results/``."""
    if not is_valid_run_id(run_id):
        raise ValueError(f"{run_id!r} is not a valid run id")
    path = ensure_inside(RESULTS_DIR / run_id, RESULTS_DIR)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class RunManifest:
    """Non-sensitive record of one run. Serialised to ``manifest.json``."""

    run_id: str
    area: str
    kind: str  # "locust" | "playwright" | "combined"
    label: str = ""
    profile: str = ""
    environment: str = ""  # target host -- the thing a reader most needs to see
    config: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""
    status: str = RunStatus.PENDING.value
    exit_code: int | None = None
    redacted_command: str = ""
    redacted_commands: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    auth_method: str = "none"
    notes: list[str] = field(default_factory=list)
    diagnosis: dict[str, Any] | None = None

    # ---- lifecycle ---------------------------------------------------------

    @property
    def duration_seconds(self) -> float | None:
        start, end = _parse_iso(self.started_at), _parse_iso(self.ended_at)
        if start is None:
            return None
        end = end or datetime.now(timezone.utc)
        return max(0.0, (end - start).total_seconds())

    @property
    def status_enum(self) -> RunStatus:
        try:
            return RunStatus(self.status)
        except ValueError:
            return RunStatus.ERROR

    def mark_started(self) -> None:
        self.started_at = _now_iso()
        self.status = RunStatus.RUNNING.value

    def mark_finished(self, status: RunStatus, exit_code: int | None) -> None:
        self.ended_at = _now_iso()
        self.status = status.value
        self.exit_code = exit_code

    # ---- persistence -------------------------------------------------------

    def save(self) -> Path:
        directory = run_dir(self.run_id, create=True)
        path = directory / MANIFEST_NAME
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, run_id: str) -> "RunManifest | None":
        try:
            path = run_dir(run_id) / MANIFEST_NAME
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iter_manifests() -> Iterator[RunManifest]:
    """Every persisted run, newest first."""
    if not RESULTS_DIR.exists():
        return
    for directory in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not directory.is_dir() or not is_valid_run_id(directory.name):
            continue
        manifest = RunManifest.load(directory.name)
        if manifest is not None:
            yield manifest


def list_manifests(limit: int | None = None) -> list[RunManifest]:
    manifests = list(iter_manifests())
    return manifests[:limit] if limit else manifests


def log_path(run_id: str) -> Path:
    return run_dir(run_id) / LOG_NAME


def default_artifacts(run_id: str, kind: str) -> dict[str, str]:
    """Conventional artefact locations inside a run directory (project-relative)."""
    base = f"results/{run_id}"
    artifacts = {"log": f"{base}/{LOG_NAME}"}
    if kind in {"locust", "combined"}:
        artifacts["locust_csv_prefix"] = f"{base}/locust"
        artifacts["locust_html"] = f"{base}/locust.html"
    if kind in {"playwright", "combined"}:
        artifacts["playwright_html_dir"] = f"{base}/playwright-report"
        artifacts["playwright_json"] = f"{base}/playwright-report.json"
        artifacts["playwright_output_dir"] = f"{base}/test-results"
    return artifacts


def artifact_path(manifest: RunManifest, key: str) -> Path | None:
    value = manifest.artifacts.get(key)
    if not value:
        return None
    try:
        return ensure_inside(value, RESULTS_DIR)
    except ValueError:
        return None


def describe_run(manifest: RunManifest) -> str:
    """One-line summary for history tables."""
    duration = manifest.duration_seconds
    duration_text = f"{duration:.0f}s" if duration is not None else "-"
    return (
        f"{manifest.run_id} | {manifest.kind} | {manifest.status} | "
        f"{duration_text} | {relative_to_root(manifest.artifacts.get('log', ''))}"
    )
