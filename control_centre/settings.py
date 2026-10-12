"""Application settings: guardrails, defaults and AI-diagnosis endpoint config.

Persisted as JSON to ``config/app-settings.json``. Nothing here is a secret --
tokens live in Streamlit session memory only and are never written to disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from control_centre.paths import APP_SETTINGS_FILE, CONFIG_DIR

DEFAULT_WORKSPACE_HOST = "https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com"
DEFAULT_APP_HOST = "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
DEFAULT_SERVING_ENDPOINT = "ds-insights-companion-agent-dev"
SERVING_PATH_TEMPLATE = "/serving-endpoints/{endpoint}/invocations"


@dataclass
class Guardrails:
    """Hard ceilings the UI refuses to exceed, regardless of profile contents."""

    max_users: int = 50
    max_spawn_rate: float = 20.0
    max_run_time_seconds: int = 1800
    max_playwright_workers: int = 4
    max_repeat_each: int = 10
    # Above this user count a run is treated as a stress test and needs an
    # explicit typed confirmation before it can start.
    stress_user_threshold: int = 5


@dataclass
class Thresholds:
    """Service-level expectations a run is compared against during diagnosis.

    These are the app's own reference points -- the repository does not define
    SLOs -- so they are editable and are always sent to the model alongside the
    metrics, rather than being assumed by it.
    """

    max_failure_pct: float = 1.0
    max_p95_ms: float = 5000.0
    max_avg_ms: float = 3000.0
    min_requests_per_second: float = 0.0
    max_playwright_journey_ms: float = 120_000.0


@dataclass
class DiagnosisSettings:
    """Where the LLM diagnosis request is sent and how it is shaped."""

    workspace_host: str = DEFAULT_WORKSPACE_HOST
    endpoint_name: str = "databricks-claude-sonnet-4-5"
    # "chat" -> OpenAI-compatible {"messages": [...]}, used by AI Gateway and
    # foundation-model serving endpoints.
    # "responses_agent" -> MLflow ResponsesAgent {"input": [...]}, the shape this
    # repo's own ds-insights-companion-agent-dev endpoint speaks.
    payload_style: str = "chat"
    auth_method: str = "oauth_u2m"
    timeout_seconds: int = 180
    max_tokens: int = 1400
    temperature: float = 0.0


@dataclass
class AppSettings:
    """Everything the control centre remembers between sessions."""

    guardrails: Guardrails = field(default_factory=Guardrails)
    thresholds: Thresholds = field(default_factory=Thresholds)
    diagnosis: DiagnosisSettings = field(default_factory=DiagnosisSettings)
    default_workspace_host: str = DEFAULT_WORKSPACE_HOST
    default_app_host: str = DEFAULT_APP_HOST
    default_serving_endpoint: str = DEFAULT_SERVING_ENDPOINT
    # Hosts treated as production: the UI shows a prominent reminder for them.
    # "adidas-lh-wrk-gazelle." is this project's production workspace, whose host
    # carries no generic prod marker (the dev workspace is adidas-dwhm-lh-wrk-gazelle-dev).
    production_host_markers: list[str] = field(
        default_factory=lambda: ["-prod", "prd", "production", "adidas-lh-wrk-gazelle."]
    )
    auto_refresh_seconds: int = 2
    log_tail_lines: int = 400

    # ---- persistence -------------------------------------------------------

    @classmethod
    def load(cls) -> "AppSettings":
        if not APP_SETTINGS_FILE.exists():
            return cls()
        try:
            raw: dict[str, Any] = json.loads(APP_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        settings = cls()
        settings.guardrails = Guardrails(**{**asdict(settings.guardrails), **raw.get("guardrails", {})})
        settings.thresholds = Thresholds(**{**asdict(settings.thresholds), **raw.get("thresholds", {})})
        settings.diagnosis = DiagnosisSettings(**{**asdict(settings.diagnosis), **raw.get("diagnosis", {})})
        for key in (
            "default_workspace_host",
            "default_app_host",
            "default_serving_endpoint",
            "production_host_markers",
            "auto_refresh_seconds",
            "log_tail_lines",
        ):
            if key in raw:
                setattr(settings, key, raw[key])
        return settings

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        APP_SETTINGS_FILE.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    # ---- helpers -----------------------------------------------------------

    def is_production_host(self, host: str) -> bool:
        lowered = (host or "").lower()
        return any(marker.lower() in lowered for marker in self.production_host_markers)

    def serving_path(self, endpoint: str | None = None) -> str:
        return SERVING_PATH_TEMPLATE.format(endpoint=endpoint or self.default_serving_endpoint)
