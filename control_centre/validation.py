"""Validation of user-supplied run configuration.

Every value the UI collects passes through here before a command is built.
Validation is deliberately conservative: anything that cannot be proven safe
(unparseable duration, URL without a scheme, output path outside ``results/``)
is an error rather than a best-effort guess.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from control_centre.discovery import find_playwright_test, find_scenario, scenario_env_requirements
from control_centre.models import (
    CombinedRunConfig,
    LocustRunConfig,
    PlaywrightRunConfig,
    ValidationResult,
)
from control_centre.paths import (
    PROJECT_ROOT,
    RESULTS_DIR,
    PathOutsideProjectError,
    ensure_inside,
)
from control_centre.settings import AppSettings

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.IGNORECASE)
_ENDPOINT_PATH_RE = re.compile(r"^/serving-endpoints/[A-Za-z0-9._\-]+/invocations$")
_ENDPOINT_NAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")

TRACE_CHOICES = ("off", "on", "retain-on-failure", "on-first-retry")
SCREENSHOT_CHOICES = ("off", "on", "only-on-failure")
VIDEO_CHOICES = ("off", "on", "retain-on-failure", "on-first-retry")


def parse_duration_seconds(value: str) -> int | None:
    """Locust ``run-time`` syntax -> seconds. ``None`` when unparseable.

    Accepts a bare integer (seconds) or any combination of ``h``/``m``/``s``
    parts, e.g. ``10s``, ``2m``, ``1h30m``.
    """
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = _DURATION_RE.fullmatch(text)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    return total or None


def validate_url(value: str, field: str, result: ValidationResult, *, require_https: bool = False) -> None:
    text = (value or "").strip()
    if not text:
        result.add(field, "Host is required.", remedy="Pick a profile or type a full URL.")
        return
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        result.add(field, f"{text!r} must start with http:// or https://")
        return
    if not parsed.netloc:
        result.add(field, f"{text!r} has no hostname.")
        return
    if parsed.query or parsed.fragment:
        result.add(field, "Host must not contain a query string or fragment.")
    if require_https and parsed.scheme != "https":
        result.add(field, "This target requires https://")
    if text.rstrip("/") != text:
        result.add(field, "Trailing slash is ignored by Locust.", severity="warning")


def validate_output_prefix(
    value: str, field: str, result: ValidationResult, *, ensure_writable: bool = True
) -> Path | None:
    """Ensure an output path stays inside ``results/``, and optionally that it is writable.

    ``ensure_writable`` is off while a run's directory is still a placeholder --
    the real ``results/<run-id>/`` is created at launch, and the writability of
    ``results/`` itself is covered by its own preflight check.
    """
    if not value:
        result.add(field, "Output path is required.")
        return None
    try:
        resolved = ensure_inside(value, RESULTS_DIR)
    except PathOutsideProjectError:
        result.add(
            field,
            f"{value!r} resolves outside the project results directory.",
            remedy="Use a path under results/.",
        )
        return None
    if not ensure_writable:
        return resolved
    parent = resolved.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.add(field, f"Cannot create output directory {parent}: {exc}")
        return None
    probe = parent / ".write-probe"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        result.add(field, f"Output directory is not writable: {exc}")
        return None
    return resolved


def validate_serving_endpoint(value: str, field: str, result: ValidationResult) -> str:
    """Accept either a bare endpoint name or a full ``/serving-endpoints/.../invocations`` path.

    Returns the normalised full path.
    """
    text = (value or "").strip()
    if not text:
        result.add(field, "Serving-endpoint name or path is required.")
        return ""
    if text.startswith("/"):
        if not _ENDPOINT_PATH_RE.fullmatch(text):
            result.add(
                field,
                "Path must look like /serving-endpoints/<endpoint-name>/invocations",
            )
            return ""
        return text
    if not _ENDPOINT_NAME_RE.fullmatch(text):
        result.add(field, "Endpoint name may only contain letters, digits, '.', '_' and '-'.")
        return ""
    return f"/serving-endpoints/{text}/invocations"


def validate_locust_config(
    config: LocustRunConfig,
    settings: AppSettings,
    *,
    auth_available: bool,
    available_env: set[str] | None = None,
) -> ValidationResult:
    result = ValidationResult()
    guards = settings.guardrails
    available_env = available_env or set()

    scenario_path = PROJECT_ROOT / config.locustfile
    if not config.locustfile:
        result.add("locustfile", "No Locust scenario selected.")
    elif not scenario_path.is_file():
        result.add(
            "locustfile",
            f"Scenario file {config.locustfile} does not exist.",
            remedy="Pick another profile or add the file under scenarios/.",
        )
    elif find_scenario(config.locustfile) is None:
        result.add(
            "locustfile",
            f"{config.locustfile} is outside scenarios/ and will not be run.",
        )

    validate_url(config.host, "host", result)

    if config.users < 1:
        result.add("users", "Users must be at least 1.")
    elif config.users > guards.max_users:
        result.add(
            "users",
            f"{config.users} users exceeds the configured guardrail of {guards.max_users}.",
            remedy="Lower the user count or raise the guardrail in Help > app settings.",
        )

    if config.spawn_rate <= 0:
        result.add("spawn_rate", "Spawn rate must be greater than 0.")
    elif config.spawn_rate > guards.max_spawn_rate:
        result.add(
            "spawn_rate",
            f"Spawn rate {config.spawn_rate} exceeds the guardrail of {guards.max_spawn_rate}.",
        )
    elif config.spawn_rate > config.users:
        result.add("spawn_rate", "Spawn rate is higher than the user count.", severity="warning")

    seconds = parse_duration_seconds(config.run_time)
    if seconds is None:
        result.add(
            "run_time",
            f"{config.run_time!r} is not a valid duration.",
            remedy="Use forms like 10s, 2m, 1h30m or a plain number of seconds.",
        )
    elif seconds > guards.max_run_time_seconds:
        result.add(
            "run_time",
            f"Run time {config.run_time} exceeds the guardrail of {guards.max_run_time_seconds}s.",
        )

    writable = config.custom_outputs
    validate_output_prefix(config.csv_prefix, "csv_prefix", result, ensure_writable=writable)
    validate_output_prefix(config.html_path, "html_path", result, ensure_writable=writable)

    required, _optional = scenario_env_requirements(config.locustfile)
    for name in required:
        if name == "BIC_AUTH_TOKEN":
            if not auth_available:
                result.add(
                    "auth",
                    f"{config.locustfile} requires BIC_AUTH_TOKEN but no token is held.",
                    remedy="Authenticate on the Authentication page.",
                )
            continue
        if not config.extra_env.get(name) and name not in available_env:
            result.add(
                "env",
                f"Required environment variable {name} is empty.",
                remedy=f"Fill in {name} in the configuration form.",
            )

    if settings.is_production_host(config.host):
        result.add(
            "host",
            "Target looks like a production host.",
            severity="warning",
            remedy="Confirm this is intended before running load.",
        )
    return result


def validate_playwright_config(
    config: PlaywrightRunConfig,
    settings: AppSettings,
    *,
    storage_state_exists: bool,
    storage_state_problem: str = "",
) -> ValidationResult:
    result = ValidationResult()
    guards = settings.guardrails

    test_path = PROJECT_ROOT / config.test_file
    if not config.test_file:
        result.add("test_file", "No Playwright spec selected.")
    elif not test_path.is_file():
        result.add("test_file", f"Test file {config.test_file} does not exist.")
    elif find_playwright_test(config.test_file) is None:
        result.add("test_file", f"{config.test_file} is outside tests/ and will not be run.")

    if not config.project:
        result.add("project", "A Playwright project (e.g. chromium) is required.")

    if config.workers < 1:
        result.add("workers", "Workers must be at least 1.")
    elif config.workers > guards.max_playwright_workers:
        result.add(
            "workers",
            f"{config.workers} workers exceeds the guardrail of {guards.max_playwright_workers}.",
        )

    if config.repeat_each < 1:
        result.add("repeat_each", "repeat-each must be at least 1.")
    elif config.repeat_each > guards.max_repeat_each:
        result.add(
            "repeat_each",
            f"repeat-each {config.repeat_each} exceeds the guardrail of {guards.max_repeat_each}.",
        )

    if config.timeout_ms < 1000:
        result.add("timeout_ms", "Test timeout must be at least 1000 ms.")
    elif config.timeout_ms > 30 * 60_000:
        result.add("timeout_ms", "Test timeout above 30 minutes is almost certainly a mistake.")

    validate_url(config.base_url, "base_url", result)

    if config.trace not in TRACE_CHOICES:
        result.add("trace", f"trace must be one of {', '.join(TRACE_CHOICES)}.")
    if config.screenshot not in SCREENSHOT_CHOICES:
        result.add("screenshot", f"screenshot must be one of {', '.join(SCREENSHOT_CHOICES)}.")
    if config.video not in VIDEO_CHOICES:
        result.add("video", f"video must be one of {', '.join(VIDEO_CHOICES)}.")

    if not storage_state_exists:
        result.add(
            "storage_state",
            "Saved Playwright session playwright/.auth/bic-user.json is missing.",
            remedy="Run 'Capture browser session' on the Authentication page.",
        )
    elif storage_state_problem:
        # An expired Databricks Apps session redirects to SSO, so the test would
        # only fail after its full timeout waiting for the app to render.
        result.add(
            "storage_state",
            storage_state_problem,
            remedy="Authentication > Browser session > Capture browser session (the app session lasts about 24h).",
        )

    for field, value in (
        ("html_report_dir", config.html_report_dir),
        ("json_report_path", config.json_report_path),
        ("output_dir", config.output_dir),
    ):
        validate_output_prefix(value, field, result, ensure_writable=config.custom_outputs)

    if settings.is_production_host(config.base_url):
        result.add("base_url", "Target looks like a production host.", severity="warning")
    return result


def validate_combined_config(
    config: CombinedRunConfig,
    settings: AppSettings,
    *,
    auth_available: bool,
    storage_state_exists: bool,
    storage_state_problem: str = "",
    available_env: set[str] | None = None,
) -> ValidationResult:
    result = validate_locust_config(
        config.locust, settings, auth_available=auth_available, available_env=available_env
    )
    result.merge(
        validate_playwright_config(
            config.playwright,
            settings,
            storage_state_exists=storage_state_exists,
            storage_state_problem=storage_state_problem,
        )
    )
    if config.warmup_seconds < 0:
        result.add("warmup_seconds", "Warm-up must be 0 or more seconds.")
    run_seconds = parse_duration_seconds(config.locust.run_time)
    if run_seconds is not None and config.warmup_seconds >= run_seconds:
        result.add(
            "warmup_seconds",
            "Warm-up is not shorter than the Locust run time -- the UI journey would start after load ends.",
        )
    return result


def requires_stress_confirmation(config: LocustRunConfig, settings: AppSettings) -> bool:
    """True when this run counts as a stress profile and needs typed confirmation."""
    return config.users > settings.guardrails.stress_user_threshold
