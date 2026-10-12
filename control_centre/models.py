"""Structured models shared by discovery, validation, execution and reporting."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TestArea(str, enum.Enum):
    """Top-level thing under test."""

    BFF = "fastapi_bff"
    UI = "react_ui"
    SERVING = "serving_endpoint"
    COMBINED = "combined"

    @property
    def label(self) -> str:
        return {
            TestArea.BFF: "FastAPI BFF",
            TestArea.UI: "React UI",
            TestArea.SERVING: "Serving endpoint",
            TestArea.COMBINED: "Combined load + UI",
        }[self]


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ERROR = "error"

    @property
    def is_terminal(self) -> bool:
        return self is not RunStatus.RUNNING and self is not RunStatus.PENDING


class AuthMethod(str, enum.Enum):
    NONE = "none"
    OAUTH_U2M = "oauth_u2m"
    PAT = "pat"
    PLAYWRIGHT_STATE = "playwright_storage_state"

    @property
    def label(self) -> str:
        return {
            AuthMethod.NONE: "No auth (local BFF)",
            AuthMethod.OAUTH_U2M: "Databricks CLI OAuth U2M",
            AuthMethod.PAT: "Personal access token (PAT)",
            AuthMethod.PLAYWRIGHT_STATE: "Saved Playwright browser session",
        }[self]


@dataclass(frozen=True)
class LocustProfile:
    """A discovered Locust ``.conf`` file with its parsed key/value defaults."""

    name: str
    path: Path
    values: dict[str, str]
    description: str = ""
    area: TestArea = TestArea.BFF

    @property
    def locustfile(self) -> str:
        return self.values.get("locustfile", "")

    @property
    def host(self) -> str:
        return self.values.get("host", "")

    @property
    def users(self) -> int:
        try:
            return int(self.values.get("users", "1"))
        except ValueError:
            return 1

    @property
    def is_stress(self) -> bool:
        return self.users > 1


@dataclass(frozen=True)
class LocustScenario:
    """A discovered ``scenarios/*.py`` Locust file."""

    name: str
    path: Path
    summary: str
    required_env: tuple[str, ...] = ()
    optional_env: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaywrightTest:
    """A discovered ``tests/*.spec.ts`` Playwright spec."""

    name: str
    path: Path
    titles: tuple[str, ...]
    summary: str
    is_recorded_draft: bool = False


@dataclass
class LocustRunConfig:
    """Fully resolved, validated Locust run settings for one execution."""

    profile_name: str
    locustfile: str
    host: str
    users: int
    spawn_rate: float
    run_time: str
    headless: bool = True
    csv_prefix: str = ""
    html_path: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)
    # True when the user overrode the run-scoped output paths by hand, so the
    # orchestrator must not re-point them at results/<run-id>/.
    custom_outputs: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "locustfile": self.locustfile,
            "host": self.host,
            "users": self.users,
            "spawn_rate": self.spawn_rate,
            "run_time": self.run_time,
            "headless": self.headless,
            "csv_prefix": self.csv_prefix,
            "html_path": self.html_path,
            "env_keys": sorted(self.extra_env),
        }


@dataclass
class PlaywrightRunConfig:
    """Fully resolved, validated Playwright run settings for one execution."""

    test_file: str
    project: str = "chromium"
    headed: bool = False
    workers: int = 1
    repeat_each: int = 1
    base_url: str = ""
    timeout_ms: int = 120_000
    storage_state: str = ""
    html_report_dir: str = ""
    json_report_path: str = ""
    output_dir: str = ""
    trace: str = "retain-on-failure"
    screenshot: str = "only-on-failure"
    video: str = "off"
    grep: str = ""
    custom_outputs: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "test_file": self.test_file,
            "project": self.project,
            "headed": self.headed,
            "workers": self.workers,
            "repeat_each": self.repeat_each,
            "base_url": self.base_url,
            "timeout_ms": self.timeout_ms,
            "storage_state": self.storage_state,
            "html_report_dir": self.html_report_dir,
            "json_report_path": self.json_report_path,
            "output_dir": self.output_dir,
            "trace": self.trace,
            "screenshot": self.screenshot,
            "video": self.video,
            "grep": self.grep,
        }


@dataclass
class CombinedRunConfig:
    """Locust load with a Playwright journey layered on top of it."""

    locust: LocustRunConfig
    playwright: PlaywrightRunConfig
    warmup_seconds: int = 15
    stop_locust_after_ui: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "locust": self.locust.to_manifest(),
            "playwright": self.playwright.to_manifest(),
            "warmup_seconds": self.warmup_seconds,
            "stop_locust_after_ui": self.stop_locust_after_ui,
        }


@dataclass
class ValidationIssue:
    """One validation or preflight finding."""

    field: str
    message: str
    severity: str = "error"  # "error" blocks Run; "warning" does not
    remedy: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity == "error"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, field_name: str, message: str, severity: str = "error", remedy: str = "") -> None:
        self.issues.append(ValidationIssue(field_name, message, severity, remedy))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.blocking]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if not i.blocking]

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.issues.extend(other.issues)
        return self
